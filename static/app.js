'use strict';

// ------------------------------------------------------------------ utilidades

const $ = (sel) => document.querySelector(sel);

const estado = {
    info: { escola: '', cidade: '' },
    usuarios: [],
    perfis: [],
    selecionados: new Set(),
    conectados: [],
    aparelhos: [],
    rede: [],
    importacao: [],
    importados: [],
    editandoUsuario: null,
    editandoAparelho: null,
    abaAtual: 'usuarios',
    relogioConectados: null,
};

class ErroApi extends Error {
    constructor(mensagem, status) { super(mensagem); this.status = status; }
}

async function api(metodo, url, corpo) {
    const opcoes = { method: metodo, headers: { 'X-Painel': '1' }, credentials: 'same-origin' };
    if (corpo instanceof FormData) {
        opcoes.body = corpo;
    } else if (corpo !== undefined) {
        opcoes.headers['Content-Type'] = 'application/json';
        opcoes.body = JSON.stringify(corpo);
    }
    let resposta;
    try {
        resposta = await fetch(url, opcoes);
    } catch (e) {
        throw new ErroApi('Sem conexão com o painel.', 0);
    }
    let dados = null;
    try { dados = await resposta.json(); } catch (e) { /* resposta vazia */ }
    if (!resposta.ok) {
        let mensagem = (dados && dados.erro) || 'Erro ' + resposta.status;
        if (dados && Array.isArray(dados.detail)) mensagem = 'Dados inválidos: confira os campos.';
        if (resposta.status === 401 && url !== '/api/login') {
            mostrarLogin(mensagem);
        }
        throw new ErroApi(mensagem, resposta.status);
    }
    return dados;
}

// Cria elementos sem innerHTML: textos vindos do MikroTik nunca viram HTML.
function el(tag, props, ...filhos) {
    const elemento = document.createElement(tag);
    for (const [chave, valor] of Object.entries(props || {})) {
        if (valor === null || valor === undefined || valor === false) continue;
        if (chave === 'class') elemento.className = valor;
        else if (chave === 'texto') elemento.textContent = valor;
        else if (chave.startsWith('on')) elemento.addEventListener(chave.slice(2), valor);
        else if (chave === 'dados') Object.assign(elemento.dataset, valor);
        else elemento.setAttribute(chave, valor === true ? '' : valor);
    }
    for (const filho of filhos.flat()) {
        if (filho === null || filho === undefined || filho === false) continue;
        elemento.append(filho instanceof Node ? filho : document.createTextNode(String(filho)));
    }
    return elemento;
}

let relogioAviso = null;
function aviso(mensagem, erro) {
    const caixa = $('#aviso');
    caixa.textContent = mensagem;
    caixa.className = erro ? 'aviso erro' : 'aviso';
    caixa.hidden = false;
    clearTimeout(relogioAviso);
    relogioAviso = setTimeout(() => { caixa.hidden = true; }, erro ? 6000 : 3500);
}

function confirmar(titulo, texto, rotulo) {
    const janela = $('#janela-confirmar');
    $('#confirmar-titulo').textContent = titulo;
    $('#confirmar-texto').textContent = texto;
    $('#confirmar-sim').textContent = rotulo || 'Confirmar';
    janela.returnValue = '';
    janela.showModal();
    return new Promise((resolver) => {
        janela.addEventListener('close', () => resolver(janela.returnValue === 'sim'), { once: true });
    });
}

function bytes(n) {
    const unidades = ['B', 'KB', 'MB', 'GB', 'TB'];
    let i = 0;
    while (n >= 1024 && i < unidades.length - 1) { n /= 1024; i++; }
    return (i ? n.toFixed(1).replace('.', ',') : n) + ' ' + unidades[i];
}

// "1d02:03:04" / "2h5m10s" do RouterOS em texto curto.
function tempo(valor) {
    if (!valor) return '';
    return valor.replace(/(\d+)w/, '$1 sem ').replace(/(\d+)d/, '$1d ').replace(/(\d+)h/, '$1h ')
        .replace(/(\d+)m(?!s)/, '$1min ').replace(/(\d+)s/, '$1s').trim();
}

function normalizar(texto) {
    return (texto || '').toString().normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
}

function gerarSenha(tamanho) {
    const alfabeto = 'abcdefghjkmnpqrstuvwxyz23456789';
    const numeros = new Uint32Array(tamanho || 6);
    crypto.getRandomValues(numeros);
    return Array.from(numeros, (n) => alfabeto[n % alfabeto.length]).join('');
}

function lembrar(chave, valor) {
    try { localStorage.setItem('painel.' + chave, valor); } catch (e) { /* sem armazenamento */ }
}
function lembrado(chave) {
    try { return localStorage.getItem('painel.' + chave); } catch (e) { return null; }
}

function mostrarErroForm(form, mensagem) {
    const caixa = form.querySelector('[data-erro]');
    caixa.textContent = mensagem || '';
    caixa.hidden = !mensagem;
}

async function comBotao(botao, acao) {
    botao.disabled = true;
    try { return await acao(); } finally { botao.disabled = false; }
}

// ------------------------------------------------------------------ login e abas

function mostrarLogin(mensagem) {
    clearInterval(estado.relogioConectados);
    document.querySelectorAll('dialog[open]').forEach((d) => d.close());
    $('#tela-painel').hidden = true;
    $('#tela-login').hidden = false;
    const erro = $('#erro-login');
    erro.textContent = mensagem || '';
    erro.hidden = !mensagem;
    const campo = $('#form-login').usuario;
    (campo.value ? $('#form-login').senha : campo).focus();
}

function mostrarPainel(sessao) {
    $('#tela-login').hidden = true;
    $('#tela-painel').hidden = false;
    $('#usuario-logado').textContent = sessao.usuario + ' · ' + sessao.identidade;
    const conexao = $('#tipo-conexao');
    conexao.hidden = !sessao.conexao;
    conexao.textContent = sessao.conexao === 'HTTP' ? 'HTTP' : 'HTTPS';
    conexao.className = 'conexao ' + (sessao.conexao === 'HTTP' ? 'sem-cripto' : 'com-cripto');
    conexao.title = sessao.conexao === 'HTTP'
        ? 'Conexão com o MikroTik sem criptografia (serviço www). Ative o www-ssl para usar HTTPS: veja mikrotik-https.rsc.'
        : 'Conexão com o MikroTik criptografada (www-ssl).';
    abrirAba(lembrado('aba') || 'usuarios');
}

function abrirAba(nome) {
    if (!document.getElementById('aba-' + nome)) nome = 'usuarios';
    estado.abaAtual = nome;
    lembrar('aba', nome);
    document.querySelectorAll('.aba').forEach((b) => {
        const ativa = b.dataset.aba === nome;
        b.classList.toggle('ativa', ativa);
        b.setAttribute('aria-selected', ativa ? 'true' : 'false');
    });
    document.querySelectorAll('.painel-aba').forEach((s) => { s.hidden = s.id !== 'aba-' + nome; });
    clearInterval(estado.relogioConectados);
    const carregar = { usuarios: carregarUsuarios, conectados: carregarConectados, aparelhos: carregarAparelhos, importar: carregarPerfis };
    carregar[nome]().catch((e) => aviso(e.message, true));
    if (nome === 'conectados') {
        estado.relogioConectados = setInterval(() => carregarConectados().catch(() => {}), 30000);
    }
}

$('#form-login').addEventListener('submit', async (evento) => {
    evento.preventDefault();
    const form = evento.target;
    const botao = form.querySelector('button');
    await comBotao(botao, async () => {
        try {
            const sessao = await api('POST', '/api/login', { usuario: form.usuario.value.trim(), senha: form.senha.value });
            form.senha.value = '';
            mostrarPainel(sessao);
        } catch (e) {
            $('#erro-login').textContent = e.message;
            $('#erro-login').hidden = false;
            form.senha.select();
        }
    });
});

$('#sair').addEventListener('click', async () => {
    try { await api('POST', '/api/logout'); } catch (e) { /* já saiu */ }
    mostrarLogin();
});

document.querySelectorAll('.aba').forEach((b) => b.addEventListener('click', () => abrirAba(b.dataset.aba)));
document.querySelectorAll('[data-fechar]').forEach((b) => b.addEventListener('click', () => b.closest('dialog').close()));

// ------------------------------------------------------------------ perfis

async function carregarPerfis() {
    estado.perfis = await api('GET', '/api/perfis');
    const opcoes = () => estado.perfis.map((p) => el('option', { value: p, texto: p }));
    const filtro = $('#filtro-perfil');
    const atual = filtro.value;
    filtro.replaceChildren(el('option', { value: '', texto: 'Todos os perfis' }), ...opcoes());
    filtro.value = estado.perfis.includes(atual) ? atual : '';
    $('#form-usuario').perfil.replaceChildren(...opcoes());
    const importar = $('#perfil-importar');
    const escolhido = importar.value || lembrado('perfil') || '';
    importar.replaceChildren(...opcoes());
    if (estado.perfis.includes(escolhido)) importar.value = escolhido;
}

// ------------------------------------------------------------------ usuários

async function carregarUsuarios() {
    const [usuarios] = await Promise.all([api('GET', '/api/usuarios'), carregarPerfis()]);
    estado.usuarios = usuarios;
    const ids = new Set(usuarios.map((u) => u.id));
    for (const id of [...estado.selecionados]) if (!ids.has(id)) estado.selecionados.delete(id);
    renderUsuarios();
}

function usuariosFiltrados() {
    const busca = normalizar($('#busca-usuarios').value);
    const perfil = $('#filtro-perfil').value;
    return estado.usuarios.filter((u) =>
        (!perfil || u.perfil === perfil) &&
        (!busca || normalizar(u.nome + ' ' + u.comentario).includes(busca)));
}

function renderUsuarios() {
    const lista = usuariosFiltrados();
    const corpo = $('#lista-usuarios');
    corpo.replaceChildren();
    if (!lista.length) {
        corpo.append(el('tr', {}, el('td', { colspan: 8, class: 'vazio', texto: estado.usuarios.length ? 'Nenhum usuário encontrado.' : 'Nenhum usuário cadastrado ainda.' })));
    }
    for (const u of lista) {
        const marcado = estado.selecionados.has(u.id);
        corpo.append(el('tr', { class: u.desativado ? 'inativo' : '' },
            el('td', { class: 'col-check' }, el('input', {
                type: 'checkbox', checked: marcado, 'aria-label': 'Selecionar ' + u.nome,
                onchange: (e) => { e.target.checked ? estado.selecionados.add(u.id) : estado.selecionados.delete(u.id); atualizarSelecao(); },
            })),
            el('td', {}, el('strong', { texto: u.nome })),
            el('td', { 'data-rotulo': 'Senha', class: 'mono', texto: u.senha || '—' }),
            el('td', { 'data-rotulo': 'Nome', texto: u.comentario }),
            el('td', { 'data-rotulo': 'Perfil', texto: u.perfil }),
            el('td', { 'data-rotulo': 'Limite', texto: u.limite_tempo ? tempo(u.limite_tempo) : '—' }),
            el('td', {}, u.desativado
                ? el('span', { class: 'etiqueta off', texto: 'Desativado' })
                : el('span', { class: 'etiqueta ok', texto: 'Ativo' }),
                u.mac ? el('span', { class: 'etiqueta bypass', title: u.mac, texto: ' preso ao aparelho' }) : null),
            el('td', {}, el('div', { class: 'acoes' },
                el('button', { class: 'botao pequeno', type: 'button', texto: 'Editar', onclick: () => abrirUsuario(u) }),
                el('button', { class: 'botao pequeno', type: 'button', texto: u.desativado ? 'Ativar' : 'Desativar', onclick: () => alternarUsuario(u) }),
                el('button', { class: 'botao pequeno', type: 'button', texto: 'Excluir', onclick: () => excluirUsuario(u) }),
            )),
        ));
    }
    const ativos = estado.usuarios.filter((u) => !u.desativado).length;
    $('#resumo-usuarios').textContent = `${estado.usuarios.length} usuário(s), ${ativos} ativo(s)` +
        (lista.length !== estado.usuarios.length ? ` · mostrando ${lista.length}` : '');
    atualizarSelecao();
}

function atualizarSelecao() {
    const visiveis = usuariosFiltrados();
    const n = estado.selecionados.size;
    $('#barra-selecao').hidden = n === 0;
    $('#qtd-selecionados').textContent = n === 1 ? '1 selecionado' : n + ' selecionados';
    const todos = $('#marcar-todos');
    const marcadosVisiveis = visiveis.filter((u) => estado.selecionados.has(u.id)).length;
    todos.checked = visiveis.length > 0 && marcadosVisiveis === visiveis.length;
    todos.indeterminate = marcadosVisiveis > 0 && marcadosVisiveis < visiveis.length;
}

$('#busca-usuarios').addEventListener('input', renderUsuarios);
$('#filtro-perfil').addEventListener('change', renderUsuarios);
$('#marcar-todos').addEventListener('change', (e) => {
    for (const u of usuariosFiltrados()) e.target.checked ? estado.selecionados.add(u.id) : estado.selecionados.delete(u.id);
    renderUsuarios();
});

function abrirUsuario(usuario) {
    const form = $('#form-usuario');
    estado.editandoUsuario = usuario || null;
    form.reset();
    mostrarErroForm(form, '');
    $('#titulo-usuario').textContent = usuario ? 'Editar ' + usuario.nome : 'Novo usuário';
    $('#ajuda-senha').hidden = !usuario;
    form.senha.required = !usuario;
    if (usuario) {
        form.nome.value = usuario.nome;
        form.senha.value = '';
        form.senha.placeholder = usuario.senha ? 'atual: ' + usuario.senha : '';
        form.comentario.value = usuario.comentario;
        form.perfil.value = usuario.perfil;
        form.limite_tempo.value = usuario.limite_tempo;
        form.mac.value = usuario.mac;
    } else {
        form.senha.value = gerarSenha();
        form.senha.placeholder = '';
        const perfil = lembrado('perfil');
        if (perfil && estado.perfis.includes(perfil)) form.perfil.value = perfil;
    }
    $('#janela-usuario').showModal();
    form.nome.focus();
}

$('#novo-usuario').addEventListener('click', () => abrirUsuario(null));
$('#gerar-senha').addEventListener('click', () => { $('#form-usuario').senha.value = gerarSenha(); });

$('#form-usuario').addEventListener('submit', async (evento) => {
    evento.preventDefault();
    const form = evento.target;
    const dados = {
        nome: form.nome.value.trim(),
        senha: form.senha.value,
        perfil: form.perfil.value,
        comentario: form.comentario.value.trim(),
        limite_tempo: form.limite_tempo.value.trim(),
        mac: form.mac.value.trim(),
    };
    const editando = estado.editandoUsuario;
    await comBotao(form.querySelector('[type=submit]'), async () => {
        try {
            if (editando) {
                if (!dados.senha) delete dados.senha;
                await api('PATCH', '/api/usuarios/' + encodeURIComponent(editando.id), dados);
                aviso('Usuário ' + dados.nome + ' alterado.');
            } else {
                await api('POST', '/api/usuarios', dados);
                lembrar('perfil', dados.perfil);
                aviso('Usuário ' + dados.nome + ' cadastrado.');
            }
            $('#janela-usuario').close();
            await carregarUsuarios();
        } catch (e) {
            mostrarErroForm(form, e.message);
        }
    });
});

async function alternarUsuario(u) {
    try {
        await api('PATCH', '/api/usuarios/' + encodeURIComponent(u.id), { desativado: !u.desativado });
        aviso(u.nome + (u.desativado ? ' ativado.' : ' desativado.'));
        await carregarUsuarios();
    } catch (e) { aviso(e.message, true); }
}

async function excluirUsuario(u) {
    if (!await confirmar('Excluir usuário', `Excluir o usuário "${u.nome}"? Ele não conseguirá mais entrar na rede.`, 'Excluir')) return;
    try {
        await api('DELETE', '/api/usuarios/' + encodeURIComponent(u.id));
        estado.selecionados.delete(u.id);
        aviso('Usuário ' + u.nome + ' excluído.');
        await carregarUsuarios();
    } catch (e) { aviso(e.message, true); }
}

$('#excluir-selecionados').addEventListener('click', async () => {
    const ids = [...estado.selecionados];
    if (!await confirmar('Excluir usuários', `Excluir ${ids.length} usuário(s) selecionado(s)? Isso não pode ser desfeito.`, 'Excluir')) return;
    try {
        const r = await api('POST', '/api/usuarios/excluir', { ids });
        estado.selecionados.clear();
        aviso(`${r.removidos} usuário(s) excluído(s).` + (r.erros.length ? ' Erros: ' + r.erros.join('; ') : ''), r.erros.length > 0);
        await carregarUsuarios();
    } catch (e) { aviso(e.message, true); }
});

$('#imprimir-selecionados').addEventListener('click', () => {
    const lista = estado.usuarios.filter((u) => estado.selecionados.has(u.id))
        .map((u) => ({ usuario: u.nome, senha: u.senha, comentario: u.comentario }));
    imprimir(lista);
});

// ------------------------------------------------------------------ conectados

async function carregarConectados() {
    estado.conectados = await api('GET', '/api/conectados');
    renderConectados();
}

function renderConectados() {
    const busca = normalizar($('#busca-conectados').value);
    const lista = estado.conectados.filter((c) => !busca || normalizar(`${c.usuario} ${c.ip} ${c.mac} ${c.comentario}`).includes(busca));
    const corpo = $('#lista-conectados');
    corpo.replaceChildren();
    if (!lista.length) {
        corpo.append(el('tr', {}, el('td', { colspan: 6, class: 'vazio', texto: estado.conectados.length ? 'Ninguém encontrado.' : 'Ninguém conectado no momento.' })));
    }
    for (const c of lista) {
        corpo.append(el('tr', {},
            el('td', {}, el('strong', { texto: c.usuario }), c.comentario ? el('div', { class: 'ajuda', texto: c.comentario }) : null),
            el('td', { 'data-rotulo': 'IP', class: 'mono', texto: c.ip }),
            el('td', { 'data-rotulo': 'MAC', class: 'mono', texto: c.mac }),
            el('td', { 'data-rotulo': 'Conectado há', texto: tempo(c.uptime) + (c.restante ? ` (restam ${tempo(c.restante)})` : '') }),
            el('td', { 'data-rotulo': 'Enviados / recebidos', texto: `${bytes(c.bytes_in)} / ${bytes(c.bytes_out)}` }),
            el('td', {}, el('div', { class: 'acoes' },
                el('button', { class: 'botao pequeno', type: 'button', texto: 'Desconectar', onclick: () => desconectar(c) }))),
        ));
    }
    const hora = new Date().toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
    $('#resumo-conectados').textContent = `${estado.conectados.length} conectado(s) · atualizado às ${hora} (a cada 30 s)`;
}

async function desconectar(c) {
    if (!await confirmar('Desconectar', `Desconectar ${c.usuario} (${c.ip})? Ele poderá entrar de novo pela tela de login.`, 'Desconectar')) return;
    try {
        await api('DELETE', '/api/conectados/' + encodeURIComponent(c.id));
        aviso(c.usuario + ' desconectado.');
        await carregarConectados();
    } catch (e) { aviso(e.message, true); }
}

$('#busca-conectados').addEventListener('input', renderConectados);
$('#atualizar-conectados').addEventListener('click', (e) => comBotao(e.target, () => carregarConectados().catch((erro) => aviso(erro.message, true))));

// ------------------------------------------------------------------ aparelhos

const NOME_TIPO = { bypassed: 'Liberado', blocked: 'Bloqueado', regular: 'Regular' };

async function carregarAparelhos() {
    estado.aparelhos = await api('GET', '/api/dispositivos');
    renderAparelhos();
}

function renderAparelhos() {
    const busca = normalizar($('#busca-aparelhos').value);
    const lista = estado.aparelhos.filter((a) => !busca || normalizar(`${a.comentario} ${a.mac} ${a.ip}`).includes(busca));
    const corpo = $('#lista-aparelhos');
    corpo.replaceChildren();
    if (!lista.length) {
        corpo.append(el('tr', {}, el('td', { colspan: 6, class: 'vazio', texto: estado.aparelhos.length ? 'Nenhum aparelho encontrado.' : 'Nenhum aparelho liberado ou bloqueado ainda.' })));
    }
    for (const a of lista) {
        const classe = a.tipo === 'bypassed' ? 'bypass' : a.tipo === 'blocked' ? 'bloqueado' : 'off';
        corpo.append(el('tr', { class: a.desativado ? 'inativo' : '' },
            el('td', {}, el('span', { class: 'etiqueta ' + classe, texto: NOME_TIPO[a.tipo] || a.tipo })),
            el('td', {}, el('strong', { texto: a.comentario || '(sem descrição)' })),
            el('td', { 'data-rotulo': 'MAC', class: 'mono', texto: a.mac || '—' }),
            el('td', { 'data-rotulo': 'IP', class: 'mono', texto: a.ip || 'qualquer' }),
            el('td', {}, a.desativado ? el('span', { class: 'etiqueta off', texto: 'Desativado' }) : el('span', { class: 'etiqueta ok', texto: 'Ativo' })),
            el('td', {}, el('div', { class: 'acoes' },
                el('button', { class: 'botao pequeno', type: 'button', texto: 'Editar', onclick: () => abrirAparelho(a.tipo, a) }),
                el('button', { class: 'botao pequeno', type: 'button', texto: a.desativado ? 'Ativar' : 'Desativar', onclick: () => alternarAparelho(a) }),
                el('button', { class: 'botao pequeno', type: 'button', texto: 'Remover', onclick: () => removerAparelho(a) }),
            )),
        ));
    }
}

function abrirAparelho(tipo, aparelho) {
    const form = $('#form-aparelho');
    estado.editandoAparelho = aparelho || null;
    form.reset();
    mostrarErroForm(form, '');
    form.tipo.value = tipo === 'blocked' ? 'blocked' : 'bypassed';
    $('#titulo-aparelho').textContent = aparelho ? 'Editar aparelho' : (tipo === 'blocked' ? 'Bloquear aparelho' : 'Liberar aparelho');
    if (aparelho) {
        form.comentario.value = aparelho.comentario;
        form.mac.value = aparelho.mac;
        form.ip.value = aparelho.ip;
    }
    $('#escolher-aparelho').open = false;
    $('#janela-aparelho').showModal();
    form.comentario.focus();
}

$('#novo-bypass').addEventListener('click', () => abrirAparelho('bypassed'));
$('#novo-bloqueio').addEventListener('click', () => abrirAparelho('blocked'));
$('#busca-aparelhos').addEventListener('input', renderAparelhos);

$('#escolher-aparelho').addEventListener('toggle', async (e) => {
    if (!e.target.open) return;
    const lista = $('#lista-rede');
    lista.replaceChildren(el('li', { texto: 'Carregando…' }));
    try {
        estado.rede = await api('GET', '/api/aparelhos');
        renderRede();
    } catch (erro) {
        lista.replaceChildren(el('li', { texto: erro.message }));
    }
});
$('#busca-rede').addEventListener('input', renderRede);

function renderRede() {
    const busca = normalizar($('#busca-rede').value);
    const lista = $('#lista-rede');
    const itens = estado.rede.filter((h) => !busca || normalizar(`${h.nome} ${h.ip} ${h.mac}`).includes(busca));
    lista.replaceChildren();
    if (!itens.length) lista.append(el('li', { texto: 'Nenhum aparelho visto na rede.' }));
    for (const h of itens) {
        const situacao = h.bypass ? 'já liberado' : h.autorizado ? 'logado' : 'sem login';
        const escolher = () => {
            const form = $('#form-aparelho');
            form.mac.value = h.mac;
            if (!form.comentario.value && h.nome) form.comentario.value = h.nome;
            $('#escolher-aparelho').open = false;
            form.comentario.focus();
        };
        lista.append(el('li', {
            tabindex: '0', onclick: escolher,
            onkeydown: (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); escolher(); } },
        },
            el('div', { class: 'nome-rede', texto: h.nome || '(sem nome)' }),
            el('div', { class: 'detalhe-rede mono', texto: `${h.mac} · ${h.ip} · ${situacao}` })));
    }
}

$('#form-aparelho').addEventListener('submit', async (evento) => {
    evento.preventDefault();
    const form = evento.target;
    const dados = { tipo: form.tipo.value, comentario: form.comentario.value.trim(), mac: form.mac.value.trim(), ip: form.ip.value.trim() };
    const editando = estado.editandoAparelho;
    await comBotao(form.querySelector('[type=submit]'), async () => {
        try {
            if (editando) {
                await api('PATCH', '/api/dispositivos/' + encodeURIComponent(editando.id), dados);
                aviso('Aparelho alterado.');
            } else {
                await api('POST', '/api/dispositivos', dados);
                aviso(dados.tipo === 'blocked' ? 'Aparelho bloqueado.' : 'Aparelho liberado.');
            }
            $('#janela-aparelho').close();
            await carregarAparelhos();
        } catch (e) {
            mostrarErroForm(form, e.message);
        }
    });
});

async function alternarAparelho(a) {
    try {
        await api('PATCH', '/api/dispositivos/' + encodeURIComponent(a.id), { desativado: !a.desativado });
        aviso((a.comentario || a.mac) + (a.desativado ? ' ativado.' : ' desativado.'));
        await carregarAparelhos();
    } catch (e) { aviso(e.message, true); }
}

async function removerAparelho(a) {
    const texto = a.tipo === 'blocked'
        ? `Remover o bloqueio de "${a.comentario || a.mac}"? O aparelho volta a poder usar a rede pelo login.`
        : `Remover a liberação de "${a.comentario || a.mac}"? O aparelho passará a precisar de login.`;
    if (!await confirmar('Remover aparelho', texto, 'Remover')) return;
    try {
        await api('DELETE', '/api/dispositivos/' + encodeURIComponent(a.id));
        aviso('Aparelho removido.');
        await carregarAparelhos();
    } catch (e) { aviso(e.message, true); }
}

// ------------------------------------------------------------------ importação

$('#form-importar').addEventListener('submit', async (evento) => {
    evento.preventDefault();
    const form = evento.target;
    const dados = new FormData();
    dados.append('arquivo', form.arquivo.files[0]);
    lembrar('perfil', form.perfil.value);
    await comBotao(form.querySelector('[type=submit]'), async () => {
        try {
            const r = await api('POST', '/api/importar/previa', dados);
            estado.importacao = r.linhas;
            estado.importados = [];
            renderImportacao();
        } catch (e) { aviso(e.message, true); }
    });
});

function renderImportacao(resultado) {
    const porUsuario = new Map((resultado || []).map((r) => [r.usuario, r]));
    const perfilPadrao = $('#perfil-importar').value;
    const corpo = $('#lista-importar');
    corpo.replaceChildren();
    for (const l of estado.importacao) {
        const r = porUsuario.get(l.usuario);
        let situacao;
        if (r) situacao = r.ok ? el('span', { class: 'etiqueta ok', texto: 'Cadastrado' }) : el('span', { class: 'etiqueta bloqueado', texto: r.erro });
        else if (l.erro) situacao = el('span', { class: 'etiqueta bloqueado', texto: l.erro });
        else situacao = el('span', { class: 'etiqueta alerta-amarelo', texto: 'Pronto para cadastrar' });
        corpo.append(el('tr', { class: l.erro ? 'inativo' : '' },
            el('td', { 'data-rotulo': 'Linha', texto: l.linha }),
            el('td', {}, el('strong', { texto: l.usuario || '(vazio)' })),
            el('td', { 'data-rotulo': 'Senha', class: 'mono', texto: l.senha + (l.senha_gerada ? ' (gerada)' : '') }),
            el('td', { 'data-rotulo': 'Nome', texto: l.comentario }),
            el('td', { 'data-rotulo': 'Perfil', texto: l.perfil || perfilPadrao }),
            el('td', {}, situacao)));
    }
    const validas = estado.importacao.filter((l) => !l.erro).length;
    const comErro = estado.importacao.length - validas;
    $('#previa-importar').hidden = false;
    if (resultado) {
        const ok = resultado.filter((r) => r.ok).length;
        $('#resumo-importar').textContent = `${ok} usuário(s) cadastrado(s)` + (resultado.length - ok ? `, ${resultado.length - ok} com erro.` : '.');
        $('#confirmar-importar').hidden = true;
        $('#imprimir-importados').hidden = ok === 0;
    } else {
        $('#resumo-importar').textContent = `${estado.importacao.length} linha(s): ${validas} pronta(s) para cadastrar` + (comErro ? `, ${comErro} com problema (serão ignoradas).` : '.');
        $('#confirmar-importar').hidden = validas === 0;
        $('#confirmar-importar').textContent = `Cadastrar ${validas} usuário(s)`;
        $('#imprimir-importados').hidden = true;
    }
}

$('#confirmar-importar').addEventListener('click', async (evento) => {
    const linhas = estado.importacao.filter((l) => !l.erro)
        .map((l) => ({ usuario: l.usuario, senha: l.senha, comentario: l.comentario, perfil: l.perfil }));
    await comBotao(evento.target, async () => {
        try {
            const r = await api('POST', '/api/importar', { perfil: $('#perfil-importar').value, linhas });
            const ok = new Set(r.resultado.filter((x) => x.ok).map((x) => x.usuario));
            estado.importados = estado.importacao.filter((l) => ok.has(l.usuario))
                .map((l) => ({ usuario: l.usuario, senha: l.senha, comentario: l.comentario }));
            renderImportacao(r.resultado);
            aviso(`${r.criados} usuário(s) cadastrado(s).`);
        } catch (e) { aviso(e.message, true); }
    });
});

$('#imprimir-importados').addEventListener('click', () => imprimir(estado.importados));

// ------------------------------------------------------------------ impressão

function imprimir(lista) {
    if (!lista.length) { aviso('Nada para imprimir.', true); return; }
    const area = $('#impressao');
    area.replaceChildren(...lista.map((c) => el('div', { class: 'credencial' },
        el('div', { class: 'credencial-topo' },
            el('img', { src: '/static/logo.png', alt: '' }),
            el('strong', { texto: 'Wi-Fi da Escola' })),
        el('div', { class: 'credencial-escola', texto: estado.info.escola }),
        el('div', { class: 'credencial-nome', texto: c.comentario || '' }),
        el('div', { class: 'credencial-campo' }, 'Usuário', el('b', { texto: c.usuario })),
        el('div', { class: 'credencial-campo' }, 'Senha', el('b', { texto: c.senha || '(não disponível)' })),
    )));
    window.print();
}

// ------------------------------------------------------------------ início

(async function iniciar() {
    try {
        estado.info = await api('GET', '/api/info');
        const texto = estado.info.escola + (estado.info.cidade ? ' · ' + estado.info.cidade : '');
        document.querySelectorAll('[data-escola]').forEach((e) => { e.textContent = texto; });
    } catch (e) { /* segue sem o nome */ }
    try {
        mostrarPainel(await api('GET', '/api/sessao'));
    } catch (e) {
        mostrarLogin();
    }
})();
