'use strict';
// Abas da versão 1.1: perfis e horário, sites bloqueados, consumo, aviso,
// histórico e backup. Usa as funções de app.js ($, el, api, aviso, confirmar...).

const NOMES_DIAS = { mon: 'seg', tue: 'ter', wed: 'qua', thu: 'qui', fri: 'sex', sat: 'sáb', sun: 'dom' };

function textoDias(dias) {
    const chave = dias.join(',');
    if (chave === 'mon,tue,wed,thu,fri') return 'seg a sex';
    if (chave === 'mon,tue,wed,thu,fri,sat') return 'seg a sáb';
    if (chave === 'mon,tue,wed,thu,fri,sat,sun') return 'todos os dias';
    return dias.map((d) => NOMES_DIAS[d] || d).join(', ');
}

function velocidade(mbps) {
    if (!mbps) return 'sem limite';
    return (mbps < 1 ? Math.round(mbps * 1000) + ' kbps' : String(mbps).replace('.', ',') + ' Mbps');
}

function dataHora(iso) {
    if (!iso) return '';
    const d = new Date(iso.replace(' ', 'T'));
    if (isNaN(d)) return iso;
    return d.toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function linhaVazia(corpo, colunas, texto) {
    corpo.append(el('tr', {}, el('td', { colspan: colunas, class: 'vazio', texto })));
}

// ------------------------------------------------------------------ perfis e horário

estado.perfisDetalhes = [];
estado.editandoPerfil = null;
estado.horarioPerfil = null;

async function carregarPerfisDetalhes() {
    estado.perfisDetalhes = await api('GET', '/api/perfis/detalhes');
    const corpo = $('#lista-perfis');
    corpo.replaceChildren();
    if (!estado.perfisDetalhes.length) linhaVazia(corpo, 8, 'Nenhum perfil.');
    for (const p of estado.perfisDetalhes) {
        const h = p.horario || {};
        corpo.append(el('tr', {},
            el('td', {}, el('strong', { texto: p.nome }), p.padrao ? el('span', { class: 'etiqueta off', texto: ' padrão' }) : null),
            el('td', { 'data-rotulo': 'Download', texto: velocidade(p.download_mbps) }),
            el('td', { 'data-rotulo': 'Envio', texto: velocidade(p.envio_mbps) }),
            el('td', { 'data-rotulo': 'Aparelhos', texto: p.aparelhos ? String(p.aparelhos) : 'sem limite' }),
            el('td', { 'data-rotulo': 'Sessão', texto: p.tempo_sessao ? tempo(p.tempo_sessao) : 'sem limite' }),
            el('td', { 'data-rotulo': 'Horário' }, h.ativo
                ? el('span', { class: 'etiqueta bypass', texto: `${h.inicio}–${h.fim}, ${textoDias(h.dias)}` })
                : el('span', { class: 'etiqueta off', texto: 'livre' })),
            el('td', { 'data-rotulo': 'Usuários', texto: String(p.usuarios) }),
            el('td', {}, el('div', { class: 'acoes' },
                el('button', { class: 'botao pequeno cor-azul', type: 'button', texto: 'Editar', onclick: () => abrirPerfil(p) }),
                el('button', { class: 'botao pequeno cor-teal', type: 'button', texto: 'Horário', onclick: () => abrirHorario(p) }),
                p.padrao ? null : el('button', { class: 'botao pequeno cor-vermelho', type: 'button', texto: 'Excluir', onclick: () => excluirPerfil(p) }),
            )),
        ));
    }
}

function abrirPerfil(perfil) {
    const form = $('#form-perfil');
    estado.editandoPerfil = perfil || null;
    form.reset();
    mostrarErroForm(form, '');
    $('#titulo-perfil').textContent = perfil ? 'Editar perfil ' + perfil.nome : 'Novo perfil';
    form.nome.disabled = !!(perfil && perfil.padrao);
    if (perfil) {
        form.nome.value = perfil.nome;
        form.download_mbps.value = perfil.download_mbps || '';
        form.envio_mbps.value = perfil.envio_mbps || '';
        form.aparelhos.value = perfil.aparelhos;
        form.tempo_sessao.value = perfil.tempo_sessao;
    } else {
        form.aparelhos.value = 1;
    }
    $('#janela-perfil').showModal();
    form.nome.focus();
}

$('#novo-perfil').addEventListener('click', () => abrirPerfil(null));

$('#form-perfil').addEventListener('submit', async (evento) => {
    evento.preventDefault();
    const form = evento.target;
    const numero = (campo) => (campo.value === '' ? 0 : Number(campo.value));
    const dados = {
        download_mbps: numero(form.download_mbps),
        envio_mbps: numero(form.envio_mbps),
        aparelhos: form.aparelhos.value === '' ? 1 : parseInt(form.aparelhos.value, 10),
        tempo_sessao: form.tempo_sessao.value.trim(),
    };
    if (!form.nome.disabled) dados.nome = form.nome.value.trim();
    const editando = estado.editandoPerfil;
    await comBotao(form.querySelector('[type=submit]'), async () => {
        try {
            if (editando) {
                await api('PATCH', '/api/perfis/' + encodeURIComponent(editando.id), dados);
                aviso('Perfil alterado. Vale para as próximas conexões.');
            } else {
                await api('POST', '/api/perfis', dados);
                aviso('Perfil ' + dados.nome + ' criado.');
            }
            $('#janela-perfil').close();
            await carregarPerfisDetalhes();
        } catch (e) { mostrarErroForm(form, e.message); }
    });
});

async function excluirPerfil(p) {
    if (!await confirmar('Excluir perfil', `Excluir o perfil "${p.nome}"?`, 'Excluir')) return;
    try {
        await api('DELETE', '/api/perfis/' + encodeURIComponent(p.id));
        aviso('Perfil excluído.');
        await carregarPerfisDetalhes();
    } catch (e) { aviso(e.message, true); }
}

function atualizarCamposHorario() {
    const form = $('#form-horario');
    $('#campos-horario').disabled = !form.ativo.checked;
}

function abrirHorario(perfil) {
    const form = $('#form-horario');
    estado.horarioPerfil = perfil;
    form.reset();
    mostrarErroForm(form, '');
    $('#titulo-horario').textContent = 'Horário de acesso: ' + perfil.nome;
    const h = perfil.horario || {};
    form.ativo.checked = !!h.ativo;
    if (h.ativo) {
        form.inicio.value = h.inicio;
        form.fim.value = h.fim;
        form.querySelectorAll('[name=dia]').forEach((c) => { c.checked = h.dias.includes(c.value); });
    }
    atualizarCamposHorario();
    $('#janela-horario').showModal();
}

$('#form-horario').ativo.addEventListener('change', atualizarCamposHorario);

$('#form-horario').addEventListener('submit', async (evento) => {
    evento.preventDefault();
    const form = evento.target;
    const dados = {
        ativo: form.ativo.checked,
        inicio: form.inicio.value,
        fim: form.fim.value,
        dias: [...form.querySelectorAll('[name=dia]:checked')].map((c) => c.value),
    };
    await comBotao(form.querySelector('[type=submit]'), async () => {
        try {
            await api('PUT', '/api/perfis/' + encodeURIComponent(estado.horarioPerfil.id) + '/horario', dados);
            aviso(dados.ativo ? 'Horário salvo.' : 'Horário liberado.');
            $('#janela-horario').close();
            await carregarPerfisDetalhes();
        } catch (e) { mostrarErroForm(form, e.message); }
    });
});

// ------------------------------------------------------------------ sites bloqueados

estado.sites = [];

async function carregarSites() {
    estado.sites = await api('GET', '/api/bloqueios');
    renderSites();
}

function renderSites() {
    const busca = normalizar($('#busca-sites').value);
    const lista = estado.sites.filter((b) => !busca || normalizar(b.dominio + ' ' + b.motivo).includes(busca));
    const corpo = $('#lista-sites');
    corpo.replaceChildren();
    if (!lista.length) linhaVazia(corpo, 4, estado.sites.length ? 'Nenhum site encontrado.' : 'Nenhum site bloqueado.');
    for (const b of lista) {
        corpo.append(el('tr', { class: b.desativado ? 'inativo' : '' },
            el('td', {}, el('strong', { class: 'mono', texto: b.dominio })),
            el('td', { 'data-rotulo': 'Motivo', texto: b.motivo || '—' }),
            el('td', {}, b.desativado ? el('span', { class: 'etiqueta off', texto: 'Pausado' }) : el('span', { class: 'etiqueta bloqueado', texto: 'Bloqueado' })),
            el('td', {}, el('div', { class: 'acoes' },
                el('button', { class: 'botao pequeno ' + (b.desativado ? 'cor-vermelho' : 'cor-laranja'), type: 'button', texto: b.desativado ? 'Reativar' : 'Pausar', onclick: () => pausarSite(b) }),
                el('button', { class: 'botao pequeno cor-verde', type: 'button', texto: 'Desbloquear', onclick: () => desbloquearSite(b) }))),
        ));
    }
}

$('#busca-sites').addEventListener('input', renderSites);

$('#form-bloqueio').addEventListener('submit', async (evento) => {
    evento.preventDefault();
    const form = evento.target;
    await comBotao(form.querySelector('[type=submit]'), async () => {
        try {
            const r = await api('POST', '/api/bloqueios', { dominio: form.dominio.value, motivo: form.motivo.value });
            aviso(r.dominio + ' bloqueado.');
            form.reset();
            form.dominio.focus();
            await carregarSites();
        } catch (e) { aviso(e.message, true); }
    });
});

async function pausarSite(b) {
    try {
        await api('PATCH', '/api/bloqueios/' + encodeURIComponent(b.id), { desativado: !b.desativado });
        aviso(b.dominio + (b.desativado ? ' bloqueado de novo.' : ' liberado temporariamente.'));
        await carregarSites();
    } catch (e) { aviso(e.message, true); }
}

async function desbloquearSite(b) {
    if (!await confirmar('Desbloquear site', `Desbloquear ${b.dominio}?`, 'Desbloquear')) return;
    try {
        await api('DELETE', '/api/bloqueios/' + encodeURIComponent(b.id));
        aviso(b.dominio + ' desbloqueado.');
        await carregarSites();
    } catch (e) { aviso(e.message, true); }
}

// ------------------------------------------------------------------ consumo

estado.relatorio = { desde: '', usuarios: [] };
estado.agruparPor = 'usuario';

async function carregarRelatorio() {
    estado.relatorio = await api('GET', '/api/relatorio');
    renderRelatorio();
}

function renderRelatorio() {
    const { usuarios, desde } = estado.relatorio;
    const busca = normalizar($('#busca-relatorio').value);
    const total = (u) => u.bytes_in + u.bytes_out;
    const somaGeral = usuarios.reduce((s, u) => s + total(u), 0);
    const usaram = usuarios.filter((u) => total(u) > 0).length;

    $('#resumo-relatorio').replaceChildren(
        el('div', { class: 'cartao-numero' }, el('span', { texto: 'Desde' }), el('strong', { texto: desde ? dataHora(desde) : 'o início dos contadores' })),
        el('div', { class: 'cartao-numero' }, el('span', { texto: 'Total consumido' }), el('strong', { texto: bytes(somaGeral) })),
        el('div', { class: 'cartao-numero' }, el('span', { texto: 'Usuários que usaram' }), el('strong', { texto: `${usaram} de ${usuarios.length}` })),
    );

    const cabecalho = $('#cabecalho-relatorio');
    const corpo = $('#lista-relatorio');
    corpo.replaceChildren();
    let linhas;
    if (estado.agruparPor === 'turma') {
        cabecalho.replaceChildren(el('tr', {}, ...['Turma', 'Usuários', 'Usaram', 'Enviados', 'Recebidos', 'Total', '% do total'].map((t) => el('th', { texto: t }))));
        const grupos = new Map();
        for (const u of usuarios) {
            const turma = turmaDe(u.comentario) || '(sem turma)';
            const g = grupos.get(turma) || { turma, usuarios: 0, usaram: 0, bytes_in: 0, bytes_out: 0 };
            g.usuarios += 1;
            g.usaram += total(u) > 0 ? 1 : 0;
            g.bytes_in += u.bytes_in;
            g.bytes_out += u.bytes_out;
            grupos.set(turma, g);
        }
        linhas = [...grupos.values()].filter((g) => !busca || normalizar(g.turma).includes(busca))
            .sort((a, b) => total(b) - total(a));
        for (const g of linhas) {
            corpo.append(el('tr', {},
                el('td', {}, el('strong', { texto: g.turma })),
                el('td', { 'data-rotulo': 'Usuários', texto: String(g.usuarios) }),
                el('td', { 'data-rotulo': 'Usaram', texto: String(g.usaram) }),
                el('td', { 'data-rotulo': 'Enviados', texto: bytes(g.bytes_in) }),
                el('td', { 'data-rotulo': 'Recebidos', texto: bytes(g.bytes_out) }),
                el('td', { 'data-rotulo': 'Total' }, el('strong', { texto: bytes(total(g)) })),
                el('td', { 'data-rotulo': '% do total' }, barraPercentual(somaGeral ? total(g) / somaGeral : 0)),
            ));
        }
    } else {
        cabecalho.replaceChildren(el('tr', {}, ...['#', 'Usuário', 'Nome / turma', 'Tempo de uso', 'Enviados', 'Recebidos', 'Total', '% do total'].map((t) => el('th', { texto: t }))));
        linhas = usuarios.filter((u) => !busca || normalizar(u.nome + ' ' + u.comentario).includes(busca))
            .sort((a, b) => total(b) - total(a));
        linhas.forEach((u, i) => {
            corpo.append(el('tr', { class: total(u) ? '' : 'inativo' },
                el('td', { 'data-rotulo': 'Posição', texto: String(i + 1) }),
                el('td', {}, el('strong', { texto: u.nome })),
                el('td', { 'data-rotulo': 'Nome', texto: u.comentario }),
                el('td', { 'data-rotulo': 'Tempo de uso', texto: tempo(u.uptime) || '—' }),
                el('td', { 'data-rotulo': 'Enviados', texto: bytes(u.bytes_in) }),
                el('td', { 'data-rotulo': 'Recebidos', texto: bytes(u.bytes_out) }),
                el('td', { 'data-rotulo': 'Total' }, el('strong', { texto: bytes(total(u)) })),
                el('td', { 'data-rotulo': '% do total' }, barraPercentual(somaGeral ? total(u) / somaGeral : 0)),
            ));
        });
    }
    if (!linhas.length) linhaVazia(corpo, 8, 'Nada para mostrar.');
}

function barraPercentual(fracao) {
    const pct = Math.round(fracao * 1000) / 10;
    const barra = el('span', { class: 'barra-pct' }, el('span', {}));
    barra.firstChild.style.width = Math.min(100, pct) + '%';
    return el('span', { class: 'pct' }, barra, el('small', { texto: String(pct).replace('.', ',') + '%' }));
}

document.querySelectorAll('[data-agrupar]').forEach((b) => b.addEventListener('click', () => {
    estado.agruparPor = b.dataset.agrupar;
    document.querySelectorAll('[data-agrupar]').forEach((x) => x.classList.toggle('ativo', x === b));
    renderRelatorio();
}));
$('#busca-relatorio').addEventListener('input', renderRelatorio);
$('#atualizar-relatorio').addEventListener('click', (e) => comBotao(e.target, () => carregarRelatorio().catch((erro) => aviso(erro.message, true))));
$('#zerar-relatorio').addEventListener('click', async () => {
    if (!await confirmar('Zerar contadores', 'Zerar o consumo de todos os usuários? A contagem recomeça a partir de agora (útil no início de cada semana ou mês).', 'Zerar')) return;
    try {
        await api('POST', '/api/relatorio/zerar');
        aviso('Contadores zerados.');
        await carregarRelatorio();
    } catch (e) { aviso(e.message, true); }
});

// ------------------------------------------------------------------ aviso

function atualizarPreviaAviso() {
    const texto = $('#form-aviso').texto.value;
    $('#contador-aviso').textContent = `${texto.length} / 500`;
    const previa = $('#previa-aviso');
    previa.textContent = texto.trim() || '(sem aviso)';
    previa.classList.toggle('vazio-aviso', !texto.trim());
}

async function carregarAviso() {
    const r = await api('GET', '/api/aviso');
    $('#form-aviso').texto.value = r.texto;
    $('#arquivo-aviso').textContent = 'Arquivo no MikroTik: ' + r.arquivo;
    atualizarPreviaAviso();
}

async function salvarAviso(texto, botao) {
    await comBotao(botao, async () => {
        try {
            const r = await api('PUT', '/api/aviso', { texto });
            $('#form-aviso').texto.value = r.texto;
            atualizarPreviaAviso();
            aviso(r.texto ? 'Aviso publicado.' : 'Aviso apagado.');
        } catch (e) { aviso(e.message, true); }
    });
}

$('#form-aviso').texto.addEventListener('input', atualizarPreviaAviso);
$('#form-aviso').addEventListener('submit', (evento) => {
    evento.preventDefault();
    salvarAviso(evento.target.texto.value, evento.target.querySelector('[type=submit]'));
});
$('#apagar-aviso').addEventListener('click', async (evento) => {
    if (!await confirmar('Apagar aviso', 'Tirar o aviso das telas do Wi-Fi?', 'Apagar')) return;
    salvarAviso('', evento.target);
});

// ------------------------------------------------------------------ histórico

async function carregarHistorico() {
    const parametros = new URLSearchParams({
        busca: $('#busca-historico').value,
        usuario: $('#usuario-historico').value,
        dias: $('#dias-historico').value,
    });
    const itens = await api('GET', '/api/historico?' + parametros);
    const operadores = $('#usuario-historico');
    if (!operadores.value) {
        const nomes = [...new Set(itens.map((i) => i.usuario))].sort();
        operadores.replaceChildren(el('option', { value: '', texto: 'Todos os operadores' }), ...nomes.map((n) => el('option', { value: n, texto: n })));
    }
    const corpo = $('#lista-historico');
    corpo.replaceChildren();
    if (!itens.length) linhaVazia(corpo, 3, 'Nenhuma ação registrada nesse período.');
    for (const i of itens) {
        corpo.append(el('tr', {},
            el('td', { class: 'mono', texto: dataHora(i.quando) }),
            el('td', { 'data-rotulo': 'Operador' }, el('strong', { texto: i.usuario })),
            el('td', { 'data-rotulo': 'Ação', texto: i.acao })));
    }
    $('#resumo-historico').textContent = itens.length >= 1000 ? 'Mostrando as 1000 ações mais recentes.' : `${itens.length} ação(ões).`;
}

let relogioHistorico = null;
$('#busca-historico').addEventListener('input', () => {
    clearTimeout(relogioHistorico);
    relogioHistorico = setTimeout(() => carregarHistorico().catch((e) => aviso(e.message, true)), 300);
});
$('#usuario-historico').addEventListener('change', () => carregarHistorico().catch((e) => aviso(e.message, true)));
$('#dias-historico').addEventListener('change', () => carregarHistorico().catch((e) => aviso(e.message, true)));

// ------------------------------------------------------------------ backup

function resultadoRestauracao(r) {
    const partes = [`${r.usuarios} usuário(s)`, `${r.aparelhos} aparelho(s)`, `${r.perfis} perfil(is)`, `${r.bloqueios} site(s)`];
    return 'Recriados: ' + partes.join(', ') + '.' + (r.erros.length ? ' Erros: ' + r.erros.join('; ') : '');
}

async function carregarBackups() {
    const lista = await api('GET', '/api/backups');
    const corpo = $('#lista-backups');
    corpo.replaceChildren();
    if (!lista.length) linhaVazia(corpo, 6, 'Nenhum backup ainda. O primeiro é feito no próximo login.');
    for (const b of lista) {
        corpo.append(el('tr', {},
            el('td', {}, el('strong', { texto: dataHora(b.criado_em) || b.nome })),
            el('td', { 'data-rotulo': 'Usuários', texto: String(b.usuarios) }),
            el('td', { 'data-rotulo': 'Aparelhos', texto: String(b.aparelhos) }),
            el('td', { 'data-rotulo': 'Perfis', texto: String(b.perfis) }),
            el('td', { 'data-rotulo': 'Sites', texto: String(b.bloqueios) }),
            el('td', {}, el('div', { class: 'acoes' },
                el('a', { class: 'botao pequeno cor-azul', href: '/api/backups/' + encodeURIComponent(b.nome), download: b.nome, texto: 'Baixar' }),
                el('button', { class: 'botao pequeno cor-laranja', type: 'button', texto: 'Restaurar', onclick: () => restaurarBackup(b) }))),
        ));
    }
}

async function restaurarBackup(b) {
    if (!await confirmar('Restaurar backup', `Recriar no MikroTik o que estiver faltando do backup de ${dataHora(b.criado_em)}? Nada que já existe será alterado ou apagado.`, 'Restaurar')) return;
    try {
        const r = await api('POST', '/api/backups/restaurar', { nome: b.nome });
        aviso(resultadoRestauracao(r), r.erros.length > 0);
    } catch (e) { aviso(e.message, true); }
}

$('#fazer-backup').addEventListener('click', (e) => comBotao(e.target, async () => {
    try {
        await api('POST', '/api/backups');
        aviso('Backup feito.');
        await carregarBackups();
    } catch (erro) { aviso(erro.message, true); }
}));

$('#arquivo-backup').addEventListener('change', async (evento) => {
    const arquivo = evento.target.files[0];
    evento.target.value = '';
    if (!arquivo) return;
    if (!await confirmar('Restaurar backup', `Recriar no MikroTik o que estiver faltando do arquivo "${arquivo.name}"?`, 'Restaurar')) return;
    const dados = new FormData();
    dados.append('arquivo', arquivo);
    try {
        const r = await api('POST', '/api/backups/restaurar-arquivo', dados);
        aviso(resultadoRestauracao(r), r.erros.length > 0);
    } catch (e) { aviso(e.message, true); }
});

// ------------------------------------------------------------------ registro das abas

Object.assign(CARREGAR, {
    perfis: carregarPerfisDetalhes,
    sites: carregarSites,
    relatorio: carregarRelatorio,
    aviso: carregarAviso,
    historico: carregarHistorico,
    backup: carregarBackups,
});
