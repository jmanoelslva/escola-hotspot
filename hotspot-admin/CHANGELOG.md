# Changelog

Mudanças do Painel do Hotspot. Formato [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/), versões [SemVer](https://semver.org/lang/pt-BR/).

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
