# Painel do Hotspot

Aplicação web para administrar o hotspot do MikroTik (RouterOS 7) da escola, sem precisar abrir o Winbox:

- **Usuários:** listar, buscar, filtrar por turma e perfil, cadastrar, alterar, gerar senha nova com um clique, prender a um aparelho (MAC). Em lote: ativar, desativar, mudar de perfil, imprimir e excluir. Exportar para Excel (com ou sem senhas).
- **Conectados:** quem está usando a rede agora (IP, MAC, tempo, consumo), com botões para desconectar e para liberar ou bloquear o aparelho. Atualiza a cada 30 segundos.
- **Aparelhos:** liberar (bypass) TVs, impressoras e computadores da escola, ou bloquear um aparelho, pelo MAC. Dá para escolher o aparelho na lista do que está conectado, com o nome que ele informou à rede (ex.: `SamsungTV-Sala5`).
- **Perfis e horário:** velocidade de download e envio, aparelhos por usuário e tempo máximo de conexão de cada perfil; horário de acesso por perfil (ex.: alunos só das 7h às 17h, de segunda a sexta).
- **Sites bloqueados:** bloqueio pelo DNS do MikroTik (o site e todos os subdomínios), com pausa e motivo.
- **Consumo:** ranking de uso por usuário e por turma, desde o último "Zerar contadores".
- **Aviso:** texto que aparece para os alunos na tela de login e na tela de conectado do Wi-Fi.
- **Importar:** cadastrar uma turma inteira por planilha (.xlsx ou .csv). Senhas em branco são criadas pelo painel.
- **Imprimir credenciais:** cartões com usuário e senha (3 por linha numa folha A4).
- **Histórico:** quem fez o quê e quando, com busca e filtro por operador e período.
- **Backup:** uma cópia automática por dia (últimas 30) e restauração do que faltar no MikroTik.

Cada pessoa entra com um **usuário admin do próprio MikroTik**. O painel não guarda senhas em disco: a senha fica na memória só enquanto a sessão está aberta (60 minutos sem uso, por padrão). As alterações ficam registradas em `dados\acoes.log` e no log do MikroTik.

## 1. Instalar no computador Windows (automático)

1. Copie a pasta `hotspot-admin` para o computador, de preferência num caminho simples, como `C:\hotspot-admin`.
2. Dê dois cliques em **`instalar.bat`** e aceite o pedido de administrador. Ele faz tudo sozinho:
   - instala o Python 3.13 pelo `winget`, se o computador ainda não tiver;
   - instala as bibliotecas;
   - cria o `.env` já apontando para o MikroTik `192.168.88.1`;
   - cria a tarefa agendada **"Painel do Hotspot"**, que inicia o painel sempre que o computador liga (mesmo sem ninguém logado);
   - libera a porta 8080 no Firewall do Windows, só para a rede local;
   - inicia o painel e abre o navegador.
3. Entre com um **usuário admin do MikroTik**.

Outros computadores da rede acessam por `http://IP-DO-COMPUTADOR:8080` (o instalador mostra o endereço no final).

- **Atualizar:** copie os arquivos novos por cima e rode o `instalar.bat` de novo (ele mantém o `.env`).
- **Desinstalar o início automático:** `remover-inicio-automatico.bat` como administrador.
- **Log do painel:** `dados\painel.log`; ações de cada usuário: `dados\acoes.log`.
- `iniciar.bat` abre o painel numa janela, sem a tarefa agendada (para testes). Não use com a tarefa ativa: a porta já estará em uso.

## 2. MikroTik

Não precisa configurar nada: o painel usa a **REST API** do RouterOS 7 e escolhe sozinho:

- **HTTPS** (serviço `www-ssl`), se estiver ativo;
- senão **HTTP** (serviço `www`, ligado de fábrica).

O topo do painel mostra qual está em uso. Com **HTTP**, a senha do admin passa pela rede sem criptografia. Para usar HTTPS, aplique uma vez o script opcional **`mikrotik-https.rsc`** (Winbox → Files: arraste o arquivo; no New Terminal: `/import mikrotik-https.rsc`). Ele cria um certificado próprio e ativa o `www-ssl`; o painel percebe sozinho em até 5 minutos.

O usuário precisa das permissões `read`, `write`, `rest-api` e `sensitive` (o grupo `full` dos admins já tem). `sensitive` é o que permite ver e imprimir as senhas dos alunos.

## 3. Como funcionam os recursos de controle

- **Horário de acesso:** o painel coloca quem entra com o perfil numa *address list* (`painel-<perfil>`, ou a que o perfil já usava) e cria regras de firewall `drop` com horário (`time=`) para os períodos fora do permitido, com o comentário `painel-horario:<perfil> ...`, antes das outras regras da cadeia `forward`. Vale a partir do próximo login de cada usuário, e o relógio do MikroTik precisa estar certo (`/system clock`, de preferência com NTP). Conexões já aceleradas pelo *fasttrack* podem continuar alguns minutos depois do horário.
- **Sites bloqueados:** entradas em `/ip dns static` com `type=NXDOMAIN` e `match-subdomain=yes` (ou `address=0.0.0.0` em versões mais antigas do RouterOS), comentário `painel-bloqueio`. Só afetam aparelhos que usam o DNS do MikroTik. O painel só lista e remove o que ele mesmo criou.
- **Aviso:** o painel grava `aviso.txt` (o texto, para o painel ler de volta) e `aviso-escola.js` (o que as páginas carregam) na pasta de páginas do hotspot (`html-directory` do perfil, normalmente `hotspot`). As páginas do hotspot da escola (pasta `hotspot`, versão de 06/10/2026 ou mais nova) mostram o texto no login e na tela de conectado.
- **Consumo:** usa os contadores de cada usuário do hotspot. "Zerar contadores" zera todos e anota a data em `dados\relatorio.json`.
- **Backup:** feito no primeiro login de cada dia em `dados\backups` (contém as senhas dos alunos; a pasta fica só neste computador).

## 4. Planilha de importação

Baixe o modelo na aba **Importar**. A primeira linha tem os títulos; maiúsculas e acentos não importam:

| usuario | senha | nome | turma | perfil |
|---|---|---|---|---|
| maria.silva | | Maria da Silva | 9º A | |
| joao.souza | abc123 | João Souza | 1º B | alunos |

- `usuario` é obrigatória (letras sem acento, números, `.`, `-`, `_`, `@`).
- `senha` em branco: o painel gera uma de 6 caracteres, sem letras/números que se confundem no papel.
- `nome` e `turma` viram o comentário do usuário no MikroTik (`Maria da Silva - 9º A`).
- `perfil` em branco usa o perfil escolhido na tela.

O painel mostra uma prévia: linhas com problema (usuário repetido, já existente, perfil inexistente) são ignoradas. Depois de cadastrar, o botão **Imprimir credenciais** gera os cartões para entregar aos alunos.

## 5. Segurança

- O acesso ao painel (navegador → computador do painel) é HTTP dentro da rede da escola: use-o em computadores de confiança.
- Entre o painel e o MikroTik, prefira HTTPS (`mikrotik-https.rsc`).
- 5 senhas erradas seguidas bloqueiam o IP por 15 minutos.
- Reiniciar o painel desconecta todo mundo do painel (as sessões ficam só na memória).

## Desenvolvimento

```
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest -q
```

Os testes usam um MikroTik simulado (`tests/mikrotik_falso.py`) e não acessam nenhum roteador.
