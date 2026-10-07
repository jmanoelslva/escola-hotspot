# Wi-Fi da escola

Escola Estadual Professora Maria Aldineide Pessoa Gomes — Coité do Noia - AL.

| Pasta | O que é |
|---|---|
| [`hotspot/`](hotspot) | Páginas do hotspot do MikroTik (login com termos de uso, status, erros). Enviadas ao roteador pelo Winbox (Files → pasta `hotspot`). |
| [`hotspot-admin/`](hotspot-admin) | Painel do Hotspot: aplicação web (FastAPI) que administra o hotspot pela REST API do RouterOS 7. Inclui os scripts do MikroTik `mikrotik-https.rsc` e `mikrotik-redes.rsc`. Veja o [README do painel](hotspot-admin/README.md) e o [CHANGELOG](hotspot-admin/CHANGELOG.md). |
| `2026.png`, `logo.png` | Logotipo da escola (original). |

Versão atual: painel 1.17.1 — redes Administrativo (VLAN 200, hotspot) e Alunos (VLAN 300, por horário); nome, logotipo e conexão com o MikroTik ajustáveis pelo painel; administradores do MikroTik cadastrados pelo painel.

Não vão para o repositório: `hotspot-admin/.env` (endereço do MikroTik) e `hotspot-admin/dados/` (backups com as senhas dos alunos, histórico e configurações locais).
