# Changelog

Mudanças do Painel do Hotspot. Formato [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/), versões [SemVer](https://semver.org/lang/pt-BR/).

## [1.18.0] - 2026-10-07

### Adicionado
- **Pontos de acesso (APs):** cadastro em Sistema → Configurações (nome e IP). O próprio MikroTik vigia cada AP a cada 30 segundos (`/tool netwatch`, comentário `painel-ap:`), mesmo com o painel fechado. No Início, o cartão **APs** mostra quantos estão no ar e fica vermelho com o nome de quem caiu.
- **Nome da escola nas páginas do hotspot:** ao salvar Escola em Configurações, o painel grava `escola-info.js` na pasta do hotspot (nome, cidade e, no futuro, o link de troca de senha). As páginas `login.html` e `status.html` novas mostram esse nome no rodapé e nos termos de uso; é preciso enviá-las uma vez pelo Winbox.

### Alterado
- Usuários → Cadastrados não mostra mais os visitantes (eles têm a própria tela). O resumo diz quantos visitantes há; o Início conta só os usuários comuns.

## [1.17.2] - 2026-10-07

### Corrigido
- Impressão dos cartões: a primeira impressão saía sem os QR codes (e às vezes sem o logotipo), porque abria antes de as imagens carregarem. Agora espera as imagens (até 5 segundos) antes de abrir a janela de impressão.

## [1.17.1] - 2026-10-07

### Alterado
- Visitantes: o aviso de limite aparece **antes** de criar (o painel nem tenta criar quando a quantidade passa do que cabe) e diz "Limite atingido" quando não cabe mais nenhum.
- Usuários: o resumo mostra o limite da licença, quantos estão conectados e quantas sessões ainda estão disponíveis.
- Listas de usuários e visitantes em ordem natural: `visita2` antes de `visita10`.

## [1.17.0] - 2026-10-07

### Adicionado
- Início: cartão **Sessões do hotspot** ("37 de 200"), com o limite lido da licença do MikroTik (nível 4 = 200, nível 5 = 500, nível 6 = sem limite). Fica amarelo a partir de 80% e vermelho a partir de 95%. O resumo de Conectados também mostra "de 200 sessões da licença".

### Alterado
- Visitantes: até **200** senhas de uma vez (antes 50), contando as que já existem. O campo Quantidade mostra quantas ainda cabem e avisa em vermelho quando o número passa disso; o painel recusa criar além do limite.

## [1.16.1] - 2026-10-07

### Alterado
- Visitantes: criar senhas não abre mais o cartão "Senhas criadas" com os QR codes; só avisa quantas foram criadas e até quando valem (elas aparecem na lista, de onde se imprime).
- Nome do usuário: a ajuda mostra o limite de 10 letras e avisa em vermelho quando o nome passa disso e será cortado.

## [1.16.0] - 2026-10-07

### Adicionado
- Visitantes: campo **Nome do usuário** (opcional). Digitando `pais`, as senhas saem como `pais1`, `pais2`, `pais3`… (o menor número livre, sem repetir usuários que já existem). O nome vira letras minúsculas sem acento, até 10 ("Reunião" fica `reuniao`); em branco, fica `visita1`, `visita2`… O formulário mostra o exemplo enquanto se digita.

## [1.15.0] - 2026-10-07

### Alterado
- Visitantes com usuário e senha mais fáceis de digitar: usuário `visita1`, `visita2`... (o menor número livre; números de visitantes encerrados voltam a ser usados) e senha de 6 números. Antes: `vis-k7m2p` e senha com letras e números.

## [1.14.2] - 2026-10-07

### Corrigido
- `instalar.bat` encerrava **qualquer** programa que estivesse usando a porta do painel. Num PC em que a porta 8080 é redirecionada pelo Windows (`netsh portproxy`, ex.: controladora UniFi), isso mirava um `svchost` com serviços do sistema. Agora encerra só o painel antigo desta pasta (`verificar-porta.ps1`) e, se a porta estiver em uso por outro programa, para e explica como trocar a `PORTA` no `.env`.
- Rede Alunos: não aceita mais como interface a da internet (rota padrão) nem a que tem o IP pelo qual o painel fala com o MikroTik. Na lista elas aparecem como "internet/painel: não pode". Escolher a da internet e deixar "Sempre fechada" derrubava a conexão.

## [1.14.1] - 2026-10-07

### Alterado
- Rede Alunos: o modo (Por horário, Sempre aberta, Sempre fechada) virou três cartões de escolha maiores, com uma linha de explicação e a cor da situação (azul, verde, vermelho) no escolhido.

## [1.14.0] - 2026-10-07

### Adicionado
- Rede Alunos → **Interface e horários**: escolher a interface (lista do roteador, com VLANs primeiro e se está ligada) e editar os horários, cada um com início, fim e **dias da semana** próprios; "+ Adicionar horário", "Excluir", "Desfazer" e "Salvar". O painel escreve o script `painel-alunos` (formato `"08:50-09:10 12345"`, dias 0=dom … 6=sáb) e cria o script e o agendador se faltarem, então o `mikrotik-redes.rsc` deixa de ser obrigatório para esta parte. Trocar de interface religa a antiga.
- Rede Alunos → **modo**: Por horário, Sempre aberta ou Sempre fechada (agendador parado e interface ligada ou desligada).

### Alterado
- O script antigo (horários sem dias) continua funcionando e aparece como segunda a sexta; o primeiro "Salvar" grava o formato novo.

## [1.13.1] - 2026-10-07

### Alterado
- Todos os aparelhos: os totais (Logados, Sem login, Liberados, Rede sem login) têm as mesmas cores das etiquetas da lista.

## [1.13.0] - 2026-10-07

### Adicionado
- Conectados → **Todos os aparelhos**: todos os aparelhos na rede, logados no hotspot ou não. Junta o que o hotspot vê (`/ip hotspot host`, com o usuário de quem está logado) com o DHCP de todas as redes (inclusive a Alunos, que não tem login). Situação de cada um (logado, sem login, liberado, bloqueado, rede sem login), totais, filtros por rede e situação, busca, botões Liberar e Bloquear e atualização a cada 30 segundos.

## [1.12.2] - 2026-10-07

### Removido
- Textos explicativos da tela Administradores (a dica dos grupos e o aviso para quem não é full).

## [1.12.1] - 2026-10-07

### Alterado
- Administradores: só quem entrou com um usuário do grupo **full** vê os botões (novo, editar, desativar, excluir). Os demais veem só a lista e um aviso. Excluir administrador também é recusado pelo painel para quem não é full.

## [1.12.0] - 2026-10-07

### Adicionado
- Sistema → **Administradores**: usuários do próprio MikroTik (os que entram no painel). Cadastrar (senha de pelo menos 8 caracteres, com "Gerar"), trocar senha, grupo e comentário, desativar e excluir, com o último acesso de cada um. Grupo **painel** (padrão, criado sozinho: ler, alterar, REST API, ver senhas e rodar scripts; sem Winbox, SSH, reboot nem cadastrar administradores) ou **full**. Ninguém exclui, desativa ou tira do full o próprio usuário, e o último full ativo não pode sair. Trocar a própria senha mantém a sessão aberta.

### Alterado
- Agendadores criados pelo painel (visitantes e rede Alunos) têm só a política `read,write,test`, para funcionarem também com usuários do grupo painel.

## [1.11.1] - 2026-10-07

### Alterado
- "Perfis e horário" passou de Regras de acesso para **Usuários** (Cadastrados, Visitantes, Perfis e horário, Importar planilha).
- Clicar numa aba do topo sempre abre a primeira subaba (ex.: Usuários → Cadastrados); o painel não lembra mais a última subaba de cada aba. O F5 continua na mesma tela, e abrir o painel de novo começa no Início.

## [1.11.0] - 2026-10-07

### Adicionado
- Sistema → Configurações → **Escola**: nome, cidade e logotipo (PNG ou JPG, até 2 MB) do painel, da tela de entrada e dos cartões impressos, com "Voltar ao padrão". Guardados em `dados/ajustes.json` e `dados/logo.png`/`logo.jpg`, por cima do `.env`.
- Sistema → Configurações → **Conexão com o MikroTik**: IP e porta da REST API. Sem IP, fica o padrão 192.168.88.1 (ex.: só a porta mudou); sem porta, o painel tenta HTTPS e HTTP. O endereço novo é testado com o usuário logado antes de salvar; se não responder ou recusar o usuário, nada muda e a sessão continua.

## [1.10.0] - 2026-10-06

### Adicionado
- `mikrotik-redes.rsc`: redes da escola no MikroTik. Administrativo (VLAN 200, 10.0.1.1/22) com hotspot e IPv6 liberado só para quem fez login (regra por MAC criada no login e conferida a cada minuto); Alunos (VLAN 300, 10.1.0.1/21) aberta, com IPv6, isolada das outras redes e ligada só de segunda a sexta nos horários 08:50–09:10, 12:00–12:50 e 14:40–15:00 (script `painel-alunos` no próprio MikroTik, a cada minuto).
- Regras de acesso → **Rede Alunos**: estado (aberta/fechada e até quando), "Liberar agora" por 10 min a 4 h, "Fechar agora" (dentro de um horário, até o fim dele) e "Voltar ao horário normal". Funciona pelos agendadores `painel-alunos-liberado` e `painel-alunos-fechado`, que valem mesmo com o painel fechado.

### Alterado
- Perfil de usuário criado pelo painel herda os scripts de login e saída do perfil padrão (IPv6 do Administrativo).

## [1.9.1] - 2026-10-06

### Alterado
- Botões com cores leves (fundo claro, texto e borda na cor da função: azul principal, verde liberar/ativar, vermelho excluir/encerrar, laranja alterar/desativar, roxo imprimir, verde-azulado pausar, cinza cancelar). Só o "Entrar" e o botão final da janela de confirmação continuam cheios.
- Cada aba do topo tem a sua cor (Início azul, Usuários verde, Conectados verde-azulado, Aparelhos laranja, Regras de acesso roxo, Sistema cinza); a aba aberta e a subaba selecionada ganham fundo claro nessa cor.

## [1.9.0] - 2026-10-06

### Alterado
- Menus unificados: 6 abas (Início, Usuários, Conectados, Aparelhos, Regras de acesso, Sistema) com subabas. Usuários: Cadastrados, Visitantes, Importar planilha. Conectados: Conectados agora, Consumo. Regras de acesso: Perfis e horário, Sites bloqueados. Sistema: Aviso, Configurações, Backup, Histórico. O painel lembra a última subaba de cada aba e o endereço (ex.: `#usuarios/visitantes`) mantém a tela no F5.
- Atalhos "Painel do Hotspot" abrem no Chrome quando ele está instalado (também o instalado só para um usuário, achado pelo registro do Windows); o Edge fica de reserva.

### Corrigido
- `criar-atalhos.ps1 -Remover` não apagava o atalho quando recebia uma pasta só.

## [1.8.0] - 2026-10-06

### Adicionado
- Visitantes: seleção (um a um ou todos), "Imprimir selecionados", "Encerrar selecionados", "Encerrar todos" e botão para fechar o cartão "Senhas criadas". Encerrar em lote faz o mesmo que "Encerrar agora" (desconecta, apaga cookie, usuário e agendamento) e nunca mexe em usuários comuns.

## [1.7.0] - 2026-10-06

### Adicionado
- Cartões de visitante com QR codes: "1. Conecte ao Wi-Fi" (QR padrão de rede, com nome e senha configurados em Configurações → Rede Wi-Fi dos QR codes) e "2. Faça o login" (abre a tela de login do hotspot com usuário e senha preenchidos; o aceite dos termos continua obrigatório). QR gerado no próprio painel (biblioteca `segno`).

### Removido
- Envio das páginas do hotspot pelo painel (a pedido); as páginas continuam sendo enviadas pelo Winbox.

## [1.6.0] - 2026-10-06

### Adicionado
- Aba "Visitantes": senhas temporárias (1 a 50 de uma vez) válidas por 1 h a 7 dias ou até o fim do dia, com perfil e descrição, impressão dos cartões com "válido até" e "Encerrar agora". A expiração é feita pelo próprio MikroTik: um agendamento (`/system scheduler`, nome `painel-visitante-<usuário>`) desconecta, apaga o cookie, remove o usuário e se apaga na hora marcada, mesmo com o painel fechado.
- Configurações → "Páginas do hotspot": compara a pasta das páginas da escola (`PASTA_PAGINAS_HOTSPOT`, padrão `..\hotspot`) com a pasta do hotspot no roteador e envia os arquivos diferentes ou todos. O roteador baixa cada arquivo do computador do painel (`/tool fetch`) por um endereço com código temporário. Os arquivos do aviso nunca são enviados e nada é apagado no roteador.

## [1.5.0] - 2026-10-06

### Adicionado
- Aba "Configurações" com o endereço (dns-name) do hotspot: troca por perfil de servidor ou em todos os perfis em uso. Recusa `.local` e domínios em que o navegador obriga HTTPS (`.dev`, `.app` etc.) e avisa quando o nome é de um domínio da internet.

### Alterado
- CSS e scripts carregados com a versão no endereço: depois de atualizar, o navegador baixa os arquivos novos sozinho (sem Ctrl+F5).
- Abas mais compactas; no computador quebram em duas linhas quando não cabem.
- Comentário das regras de forçar DNS sem acento.

## [1.4.0] - 2026-10-06

### Adicionado
- Sites bloqueados: chave "Forçar o DNS do roteador". Ligada, regras de NAT (dstnat, redirect da porta 53 UDP/TCP, comentário `painel-forcar-dns`) mandam ao MikroTik as consultas DNS vindas das interfaces do hotspot, e o bloqueio vale também para quem configurou outro DNS. Desligar só desativa as regras; religar reaproveita. Avisa se o DNS do roteador não aceita consultas da rede.
- `painel.log` registra o resultado da verificação de atualização e as demoras do MikroTik.

## [1.3.0] - 2026-10-06

### Adicionado
- Aba "Painel geral" (a primeira): CPU, memória, temperatura, tempo ligado, modelo e versão do RouterOS, conectados e usuários cadastrados; gráfico ao vivo (a cada 2 segundos, últimos 5 minutos) de entrada e saída das interfaces escolhidas, com a interface de internet detectada pela rota padrão. Só lê enquanto a aba está aberta e visível.
- Aviso de atualização do RouterOS e do firmware da RouterBOARD: faixa no topo do painel e instruções de como atualizar. Consulta no máximo a cada 6 horas, com "Verificar agora".

## [1.2.1] - 2026-10-06

### Removido
- Instalação como app pelo navegador (PWA: manifesto, service worker e botão "Instalar app"). Os atalhos do `instalar.bat`, que abrem o painel em janela própria, continuam. O painel remove o service worker que a 1.2.0 tenha registrado.

## [1.2.0] - 2026-10-06

### Adicionado
- Painel como app: o `instalar.bat` cria os atalhos "Painel do Hotspot" na Área de Trabalho e no Menu Iniciar (todos os usuários), que abrem o painel numa janela própria do Edge ou do Chrome, com o ícone da escola (`criar-atalhos.ps1`).
- Instalável como app (PWA) no computador do painel (`http://localhost`): manifesto, ícones, service worker e botão "Instalar app".

## [1.1.2] - 2026-10-06

### Adicionado
- Backup: botão para excluir uma cópia.
- Desconectar apaga também o cookie de login automático do aparelho (perfis com login-by=cookie), para ele não entrar sozinho de novo.

## [1.1.1] - 2026-10-06

### Corrigido
- Aviso da escola: o painel grava também `aviso-escola.js`, que as páginas do hotspot carregam com <script> (a leitura de `aviso.txt` pelo navegador não funcionava no roteador).
- Conectados: botões numa linha só mesmo com login longo; IP e MAC não quebram.
- Botão "Restaurar de um arquivo" alinhado com "Fazer backup agora".

### Alterado
- Botões de ação coloridos por tipo (editar, nova senha, ativar, desativar, excluir, horário, liberar, bloquear, desconectar).
- Topo e menu alinhados com o conteúdo em telas largas.

## [1.1.0] - 2026-10-06

### Adicionado
- Usuários: filtro por turma (tirada do comentário "Nome - Turma"), ações em lote (ativar, desativar, mudar perfil), "Nova senha" com um clique e impressão do cartão, coluna de senha e exportação para Excel com ou sem senhas.
- Conectados: botões para liberar (bypass) ou bloquear o aparelho com o MAC já preenchido.
- Perfis e horário: velocidade, aparelhos por usuário e tempo de sessão de cada perfil; horário de acesso por perfil com regras de firewall.
- Sites bloqueados pelo DNS do MikroTik (NXDOMAIN, com o site e subdomínios), com pausa e motivo.
- Consumo por usuário e por turma, com "Zerar contadores".
- Aviso da escola gravado em `aviso.txt` na pasta do hotspot, mostrado nas telas de login e de conectado.
- Histórico das ações com busca e filtros.
- Backup automático diário (últimas 30 cópias), backup na hora, download e restauração (só recria o que falta).

### Alterado
- A janela de confirmação responde ao clique nos botões, sem depender do evento de fechamento do navegador.

## [1.0.0] - 2026-10-06

### Adicionado
- Usuários, conectados, aparelhos (bypass e bloqueio), importação por planilha e impressão de credenciais.
- Instalação automática no Windows (`instalar.bat`), REST API do RouterOS 7 com HTTPS ou HTTP escolhido sozinho e `mikrotik-https.rsc` para ativar o www-ssl.
