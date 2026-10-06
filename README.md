# Painel do Hotspot

Aplicação web para administrar o hotspot do MikroTik (RouterOS 7) da escola, sem precisar abrir o Winbox:

- **Usuários:** listar, buscar, cadastrar, alterar senha/perfil/nome/limite de tempo, prender a um aparelho (MAC), desativar, excluir (um ou vários).
- **Conectados:** quem está usando a rede agora (IP, MAC, tempo, consumo), com botão para desconectar. Atualiza a cada 30 segundos.
- **Aparelhos:** liberar (bypass) TVs, impressoras e computadores da escola, ou bloquear um aparelho, pelo MAC. Dá para escolher o aparelho na lista do que está conectado, com o nome que ele informou à rede (ex.: `SamsungTV-Sala5`).
- **Importar:** cadastrar uma turma inteira por planilha (.xlsx ou .csv). Senhas em branco são criadas pelo painel.
- **Imprimir credenciais:** cartões com usuário e senha (3 por linha numa folha A4) dos usuários selecionados ou recém-importados.

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

## 3. Planilha de importação

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

## Segurança

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
