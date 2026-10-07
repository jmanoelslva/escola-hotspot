# Painel do Hotspot

Aplicação web para administrar o hotspot do MikroTik (RouterOS 7) da escola, sem precisar abrir o Winbox:

O painel tem 6 abas: **Início**, **Usuários** (Cadastrados, Visitantes, Importar planilha), **Conectados** (Conectados agora, Consumo), **Aparelhos**, **Regras de acesso** (Perfis e horário, Sites bloqueados) e **Sistema** (Aviso, Configurações, Backup, Histórico).

- **Painel geral:** saúde do roteador (CPU, memória, temperatura, tempo ligado), gráfico ao vivo do tráfego das interfaces e aviso quando há RouterOS ou firmware novo.
- **Usuários:** listar, buscar, filtrar por turma e perfil, cadastrar, alterar, gerar senha nova com um clique, prender a um aparelho (MAC). Em lote: ativar, desativar, mudar de perfil, imprimir e excluir. Exportar para Excel (com ou sem senhas).
- **Conectados:** quem está usando a rede agora (IP, MAC, tempo, consumo), com botões para desconectar e para liberar ou bloquear o aparelho. Atualiza a cada 30 segundos.
- **Aparelhos:** liberar (bypass) TVs, impressoras e computadores da escola, ou bloquear um aparelho, pelo MAC. Dá para escolher o aparelho na lista do que está conectado, com o nome que ele informou à rede (ex.: `SamsungTV-Sala5`).
- **Visitantes:** senhas temporárias que expiram sozinhas (o MikroTik apaga na hora marcada), com cartões para imprimir com QR code para entrar no Wi-Fi e fazer o login.
- **Rede Alunos:** abre e fecha a rede dos alunos (VLAN 300) nos horários das aulas, com "Liberar agora" e "Fechar agora". Precisa do `mikrotik-redes.rsc` importado no MikroTik.
- **Perfis e horário:** velocidade de download e envio, aparelhos por usuário e tempo máximo de conexão de cada perfil; horário de acesso por perfil (ex.: alunos só das 7h às 17h, de segunda a sexta).
- **Sites bloqueados:** bloqueio pelo DNS do MikroTik (o site e todos os subdomínios), com pausa e motivo.
- **Consumo:** ranking de uso por usuário e por turma, desde o último "Zerar contadores".
- **Aviso:** texto que aparece para os alunos na tela de login e na tela de conectado do Wi-Fi.
- **Importar:** cadastrar uma turma inteira por planilha (.xlsx ou .csv). Senhas em branco são criadas pelo painel.
- **Imprimir credenciais:** cartões com usuário e senha (3 por linha numa folha A4).
- **Histórico:** quem fez o quê e quando, com busca e filtro por operador e período.
- **Configurações:** endereço (domínio) da tela de login do hotspot, ex.: `wifi.pmapg.internal`, e a rede Wi-Fi usada no QR code dos cartões.
- **Backup:** uma cópia automática por dia (últimas 30) e restauração do que faltar no MikroTik.

Cada pessoa entra com um **usuário admin do próprio MikroTik**. O painel não guarda senhas em disco: a senha fica na memória só enquanto a sessão está aberta (60 minutos sem uso, por padrão). As alterações ficam registradas em `dados\acoes.log` e no log do MikroTik.

## 1. Instalar no computador Windows (automático)

1. Copie a pasta `hotspot-admin` para o computador, de preferência num caminho simples, como `C:\hotspot-admin`.
2. Dê dois cliques em **`instalar.bat`** e aceite o pedido de administrador. Ele faz tudo sozinho:
   - instala o Python 3.13 pelo `winget`, se o computador ainda não tiver;
   - instala as bibliotecas;
   - cria o `.env` já apontando para o MikroTik `192.168.88.1`;
   - cria a tarefa agendada **"Painel do Hotspot"**, que inicia o painel sempre que o computador liga (mesmo sem ninguém logado);
   - cria os atalhos **"Painel do Hotspot"** na Área de Trabalho e no Menu Iniciar, que abrem o painel como um programa (janela própria do Chrome, ou do Edge se não houver Chrome, sem barra de endereço);
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
- **Forçar o DNS do roteador:** duas regras em `/ip firewall nat` (`chain=dstnat action=redirect dst-port=53 to-ports=53`, UDP e TCP, `in-interface` = interface de cada servidor de hotspot, comentário `painel-forcar-dns`). Desligar desativa as regras (`disabled=yes`), sem apagar. Precisa de `/ip dns set allow-remote-requests=yes` (o hotspot normalmente já usa). Não pega DNS criptografado (DoH/DoT) nem VPN.
- **Sites bloqueados:** entradas em `/ip dns static` com `type=NXDOMAIN` e `match-subdomain=yes` (ou `address=0.0.0.0` em versões mais antigas do RouterOS), comentário `painel-bloqueio`. Só afetam aparelhos que usam o DNS do MikroTik. O painel só lista e remove o que ele mesmo criou.
- **Aviso:** o painel grava `aviso.txt` (o texto, para o painel ler de volta) e `aviso-escola.js` (o que as páginas carregam) na pasta de páginas do hotspot (`html-directory` do perfil, normalmente `hotspot`). As páginas do hotspot da escola (pasta `hotspot`, versão de 06/10/2026 ou mais nova) mostram o texto no login e na tela de conectado.
- **Consumo:** usa os contadores de cada usuário do hotspot. "Zerar contadores" zera todos e anota a data em `dados\relatorio.json`.
- **Redes (`mikrotik-redes.rsc`):** importe pelo Winbox (Files, depois `/import mikrotik-redes.rsc`). Administrativo na VLAN 200 (10.0.1.1/22, hotspot `hotspot-adm`, perfil `hsprof-adm` copiado do `hsprof1`); Alunos na VLAN 300 (10.1.0.1/21, sem login). IPv6: um /64 do prefixo da operadora para cada rede; no Administrativo só passa para quem fez login (chain `painel-hs-v6` do firewall IPv6, regras por MAC criadas pelo on-login dos perfis e conferidas pelo agendador `painel-hs-v6`). Rede Alunos: o script `painel-alunos` roda a cada minuto e liga a `VLAN300-ALUNOS` de segunda a sexta nos horários do próprio script; o painel cria `painel-alunos-liberado` (aberta até a hora marcada) ou `painel-alunos-fechado` (fechada até o fim do horário atual). Regras criadas têm comentário `painel-redes`; o fim do arquivo traz os comandos para desfazer.
- **Visitantes:** usuários `vis-xxxxx` com comentário `painel-visitante até AAAA-MM-DD HH:MM | descrição` e um agendamento `painel-visitante-<usuário>` em `/system scheduler` que remove o usuário na hora marcada. Precisa do relógio do MikroTik certo.
- **QR codes dos visitantes:** o do Wi-Fi usa o formato padrão `WIFI:T:...;S:...;P:...;;` com o nome e a senha guardados em `dados\wifi.json` (só neste PC). O do login abre `http://<endereço do hotspot>/login?visitante=...&senha=...`; o `login.html` da escola (versão de 06/10/2026 ou mais nova) preenche os campos.
- **Backup:** feito no primeiro login de cada dia em `dados\backups` (contém as senhas dos alunos; a pasta fica só neste computador).

## 4. Planilha de importação

Baixe o modelo em **Usuários → Importar planilha**. A primeira linha tem os títulos; maiúsculas e acentos não importam:

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
