'use strict';
// Troca da própria senha do Wi-Fi (página aberta pelo link da tela de conectado).

const form = document.getElementById('form-senha');
const mensagem = document.getElementById('mensagem');

function mostrar(texto, ok) {
    mensagem.textContent = texto;
    mensagem.className = 'mensagem ' + (ok ? 'ok' : 'erro');
    mensagem.hidden = false;
}

document.getElementById('mostrar').addEventListener('change', (e) => {
    form.querySelectorAll('input[type=password], input[data-senha]').forEach((campo) => {
        campo.dataset.senha = '1';
        campo.type = e.target.checked ? 'text' : 'password';
    });
});

form.addEventListener('submit', async (evento) => {
    evento.preventDefault();
    if (form.nova.value !== form.repetir.value) {
        mostrar('A senha nova e a repetição estão diferentes.', false);
        form.repetir.focus();
        return;
    }
    const botao = form.querySelector('button');
    botao.disabled = true;
    try {
        const resposta = await fetch('/api/senha', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-Painel': '1' },
            body: JSON.stringify({ usuario: form.usuario.value.trim(), atual: form.atual.value, nova: form.nova.value }),
        });
        const dados = await resposta.json().catch(() => ({}));
        if (!resposta.ok) {
            const erro = dados.erro || (Array.isArray(dados.detail) ? 'Confira os campos.' : 'Não foi possível trocar a senha.');
            mostrar(erro, false);
            return;
        }
        form.reset();
        mostrar('Senha trocada! Use a senha nova no próximo login do Wi-Fi.', true);
    } catch (e) {
        mostrar('Sem conexão com o servidor. Tente de novo.', false);
    } finally {
        botao.disabled = false;
    }
});
