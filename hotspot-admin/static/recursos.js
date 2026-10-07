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
    const [sites] = await Promise.all([api('GET', '/api/bloqueios'), carregarForcarDns()]);
    estado.sites = sites;
    renderSites();
}

function renderForcarDns(e) {
    const chave = $('#chave-forcar-dns');
    chave.checked = e.ativo;
    chave.setAttribute('aria-checked', e.ativo ? 'true' : 'false');
    let texto = e.ativo
        ? `Ligado: as consultas DNS de ${e.interfaces.join(', ') || 'hotspot'} vão para o roteador.`
        : (e.regras ? 'Desligado (as regras continuam no MikroTik, desativadas).' : 'Desligado.');
    if (e.dns_remoto === false) texto += ' Atenção: o DNS do MikroTik não aceita consultas da rede (IP → DNS → Allow Remote Requests); sem isso, os aparelhos ficam sem internet com esta opção ligada.';
    const caixa = $('#estado-forcar-dns');
    caixa.textContent = texto;
    caixa.classList.toggle('texto-alerta', e.dns_remoto === false);
}

async function carregarForcarDns() {
    try {
        renderForcarDns(await api('GET', '/api/forcar-dns'));
    } catch (e) {
        $('#estado-forcar-dns').textContent = 'Não foi possível ler: ' + e.message;
    }
}

$('#chave-forcar-dns').addEventListener('change', async (evento) => {
    const chave = evento.target;
    const ativo = chave.checked;
    chave.disabled = true;
    try {
        renderForcarDns(await api('PUT', '/api/forcar-dns', { ativo }));
        aviso(ativo ? 'DNS do roteador forçado no hotspot.' : 'Forçar DNS desligado.');
    } catch (e) {
        chave.checked = !ativo;
        aviso(e.message, true);
    } finally {
        chave.disabled = false;
    }
});

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
                el('button', { class: 'botao pequeno cor-laranja', type: 'button', texto: 'Restaurar', onclick: () => restaurarBackup(b) }),
                el('button', { class: 'botao pequeno cor-vermelho', type: 'button', texto: 'Excluir', onclick: () => excluirBackup(b) }))),
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

async function excluirBackup(b) {
    if (!await confirmar('Excluir backup', `Excluir o backup de ${dataHora(b.criado_em) || b.nome}? O arquivo é apagado deste computador.`, 'Excluir')) return;
    try {
        await api('DELETE', '/api/backups/' + encodeURIComponent(b.nome));
        aviso('Backup excluído.');
        await carregarBackups();
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

// ------------------------------------------------------------------ configurações: endereço do hotspot

estado.perfisServidor = [];

async function carregarConfig() {
    estado.perfisServidor = await api('GET', '/api/hotspot/perfis');
    const corpo = $('#lista-perfis-servidor');
    corpo.replaceChildren();
    if (!estado.perfisServidor.length) linhaVazia(corpo, 5, 'Nenhum perfil de servidor de hotspot.');
    for (const p of estado.perfisServidor) {
        const campo = el('input', { value: p.dominio, maxlength: '200', spellcheck: 'false', autocapitalize: 'off',
            placeholder: '(usa o IP)', 'aria-label': 'Endereço do perfil ' + p.nome });
        const salvar = el('button', { class: 'botao pequeno cor-azul', type: 'button', texto: 'Salvar',
            onclick: () => comBotao(salvar, () => salvarDominio(p, campo.value)) });
        campo.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); salvar.click(); } });
        corpo.append(el('tr', { class: p.servidores.length ? '' : 'inativo' },
            el('td', {}, el('strong', { texto: p.nome }), p.padrao ? el('span', { class: 'etiqueta off', texto: ' padrão' }) : null),
            el('td', { 'data-rotulo': 'Usado por', texto: p.servidores.join(', ') || 'nenhum servidor' }),
            el('td', { 'data-rotulo': 'Endereço IP', class: 'mono', texto: p.endereco || '—' }),
            el('td', { 'data-rotulo': 'Endereço' }, campo),
            el('td', {}, el('div', { class: 'acoes' }, salvar)),
        ));
    }
    const emUso = estado.perfisServidor.find((p) => p.servidores.length && p.dominio);
    const todos = $('#form-dominio-todos').dominio;
    if (emUso && !todos.value) todos.placeholder = emUso.dominio;
}

async function salvarDominio(perfil, dominio, silencioso) {
    try {
        const r = await api('PATCH', '/api/hotspot/perfis/' + encodeURIComponent(perfil.id), { dominio });
        if (!silencioso) {
            aviso(`Perfil ${perfil.nome}: ` + (r.dominio ? `endereço agora é ${r.dominio}.` : 'usando o IP.') + (r.aviso ? ' ' + r.aviso : ''), !!r.aviso);
            await carregarConfig();
        }
        return r;
    } catch (e) {
        aviso(e.message, true);
        throw e;
    }
}

$('#form-dominio-todos').addEventListener('submit', async (evento) => {
    evento.preventDefault();
    const form = evento.target;
    const dominio = form.dominio.value.trim();
    const alvos = estado.perfisServidor.filter((p) => p.servidores.length);
    if (!alvos.length) { aviso('Nenhum perfil está em uso por um servidor de hotspot.', true); return; }
    const texto = dominio
        ? `Trocar o endereço do hotspot para "${dominio}" nos perfis ${alvos.map((p) => p.nome).join(', ')}?`
        : `Tirar o domínio dos perfis ${alvos.map((p) => p.nome).join(', ')} (o hotspot passa a usar o IP)?`;
    if (!await confirmar('Endereço do hotspot', texto, 'Aplicar')) return;
    await comBotao(form.querySelector('[type=submit]'), async () => {
        let ultimo = null;
        try {
            for (const p of alvos) ultimo = await salvarDominio(p, dominio, true);
        } catch (e) { await carregarConfig(); return; }
        aviso('Endereço do hotspot atualizado' + (ultimo && ultimo.dominio ? ` para ${ultimo.dominio}.` : ' (usando o IP).')
            + (ultimo && ultimo.aviso ? ' ' + ultimo.aviso : ''), !!(ultimo && ultimo.aviso));
        form.reset();
        await carregarConfig();
    });
});

// ------------------------------------------------------------------ todos os aparelhos na rede

estado.redeToda = { aparelhos: [], resumo: {}, redes: [] };

const SITUACAO_REDE = {
    logado: ['ok', 'Logado'],
    sem_login: ['alerta-amarelo', 'Sem login'],
    liberado: ['bypass', 'Liberado (bypass)'],
    bloqueado: ['bloqueado', 'Bloqueado'],
    sem_hotspot: ['off', 'Rede sem login'],
};

async function carregarRedeToda() {
    estado.redeToda = await api('GET', '/api/rede');
    const filtro = $('#filtro-rede');
    const atual = filtro.value;
    filtro.replaceChildren(el('option', { value: '', texto: 'Todas as redes' }),
        ...estado.redeToda.redes.map((r) => el('option', { value: r, texto: r })));
    filtro.value = estado.redeToda.redes.includes(atual) ? atual : '';
    renderRedeToda();
}

function renderRedeToda() {
    const { aparelhos, resumo } = estado.redeToda;
    const busca = normalizar($('#busca-rede-toda').value);
    const redeEscolhida = $('#filtro-rede').value;
    const situacao = $('#filtro-situacao').value;
    const lista = aparelhos.filter((a) =>
        (!redeEscolhida || a.rede === redeEscolhida) && (!situacao || a.situacao === situacao) &&
        (!busca || normalizar(`${a.nome} ${a.usuario} ${a.ip} ${a.mac}`).includes(busca)));

    $('#resumo-rede').replaceChildren(
        cartaoNumero('Aparelhos', aparelhos.length),
        cartaoNumero('Logados', resumo.logado || 0, 'ok'),
        cartaoNumero('Sem login', resumo.sem_login || 0, 'alerta-amarelo'),
        cartaoNumero('Liberados', resumo.liberado || 0, 'bypass'),
        cartaoNumero('Rede sem login', resumo.sem_hotspot || 0, 'off'));

    const corpo = $('#lista-rede-toda');
    corpo.replaceChildren();
    if (!lista.length) linhaVazia(corpo, 6, aparelhos.length ? 'Nenhum aparelho encontrado.' : 'Nenhum aparelho na rede agora.');
    for (const a of lista) {
        const [classe, rotulo] = SITUACAO_REDE[a.situacao];
        const podeMudar = a.situacao !== 'bloqueado' && a.situacao !== 'liberado' && a.situacao !== 'sem_hotspot';
        corpo.append(el('tr', { class: a.situacao === 'bloqueado' ? 'inativo' : '' },
            el('td', {}, el('strong', { texto: a.nome || '(sem nome)' }), a.usuario ? el('div', { class: 'ajuda', texto: 'usuário ' + a.usuario }) : null),
            el('td', { 'data-rotulo': 'IP', class: 'mono', texto: a.ip || '—' }),
            el('td', { 'data-rotulo': 'MAC', class: 'mono', texto: a.mac }),
            el('td', { 'data-rotulo': 'Rede', texto: a.rede || '—' }),
            el('td', {}, el('span', { class: 'etiqueta ' + classe, texto: rotulo })),
            el('td', {}, podeMudar ? el('div', { class: 'acoes' },
                el('button', { class: 'botao pequeno cor-verde', type: 'button', texto: 'Liberar', title: 'Bypass: navega sem login',
                    onclick: () => abrirAparelho('bypassed', null, { mac: a.mac, comentario: a.nome || a.usuario }) }),
                el('button', { class: 'botao pequeno cor-vermelho', type: 'button', texto: 'Bloquear',
                    onclick: () => abrirAparelho('blocked', null, { mac: a.mac, comentario: a.nome || a.usuario }) })) : null),
        ));
    }
}

// cor = a mesma classe da etiqueta da situação na lista (ok, alerta-amarelo, bypass, off).
function cartaoNumero(rotulo, valor, cor) {
    return el('div', { class: 'cartao-numero' + (cor ? ' cor-' + cor : '') }, el('span', { texto: rotulo }), el('strong', { texto: String(valor) }));
}

$('#busca-rede-toda').addEventListener('input', renderRedeToda);
$('#filtro-rede').addEventListener('change', renderRedeToda);
$('#filtro-situacao').addEventListener('change', renderRedeToda);
$('#atualizar-rede').addEventListener('click', (e) => comBotao(e.target, () => carregarRedeToda().catch((erro) => aviso(erro.message, true))));

// ------------------------------------------------------------------ administradores do MikroTik

estado.administradores = { usuarios: [], grupos: [], eu: '', eu_full: false };
estado.editandoAdministrador = null;

const AJUDA_GRUPO = {
    painel: 'Usa o painel. Sem Winbox, sem reiniciar o roteador e sem cadastrar administradores.',
    full: 'Tudo no MikroTik, inclusive Winbox e cadastrar outros administradores.',
};

async function carregarAdministradores() {
    estado.administradores = await api('GET', '/api/administradores');
    const { usuarios, eu, eu_full: full } = estado.administradores;
    // Quem não é full só vê a lista: o MikroTik não deixa esse grupo cadastrar, alterar nem excluir administradores.
    $('#novo-administrador').hidden = !full;
    const corpo = $('#lista-administradores');
    corpo.replaceChildren();
    if (!usuarios.length) linhaVazia(corpo, 6, 'Nenhum usuário.');
    for (const u of usuarios) {
        const proprio = u.nome === eu;
        corpo.append(el('tr', { class: u.desativado ? 'inativo' : '' },
            el('td', {}, el('strong', { texto: u.nome }), proprio ? el('span', { class: 'etiqueta bypass', texto: ' você' }) : null),
            el('td', { 'data-rotulo': 'Grupo' }, el('span', { class: 'etiqueta ' + (u.grupo === 'full' ? 'bloqueado' : 'off'), texto: u.grupo })),
            el('td', { 'data-rotulo': 'Comentário', texto: u.comentario || '—' }),
            el('td', { 'data-rotulo': 'Último acesso', texto: u.ultimo_acesso ? dataHora(u.ultimo_acesso) : 'nunca' }),
            el('td', {}, u.desativado ? el('span', { class: 'etiqueta off', texto: 'Desativado' }) : el('span', { class: 'etiqueta ok', texto: 'Ativo' })),
            el('td', {}, full ? el('div', { class: 'acoes' },
                el('button', { class: 'botao pequeno cor-azul', type: 'button', texto: 'Editar', onclick: () => abrirAdministrador(u) }),
                proprio ? null : el('button', { class: 'botao pequeno ' + (u.desativado ? 'cor-verde' : 'cor-laranja'), type: 'button',
                    texto: u.desativado ? 'Ativar' : 'Desativar', onclick: () => alternarAdministrador(u) }),
                proprio ? null : el('button', { class: 'botao pequeno cor-vermelho', type: 'button', texto: 'Excluir', onclick: () => excluirAdministrador(u) }),
            ) : null),
        ));
    }
}

function atualizarAjudaGrupo() {
    $('#ajuda-grupo-administrador').textContent = AJUDA_GRUPO[$('#form-administrador').grupo.value] || '';
}

function abrirAdministrador(u) {
    const form = $('#form-administrador');
    estado.editandoAdministrador = u || null;
    form.reset();
    mostrarErroForm(form, '');
    form.grupo.replaceChildren(...estado.administradores.grupos.map((g) => el('option', { value: g, texto: g })));
    $('#titulo-administrador').textContent = u ? 'Editar ' + u.nome : 'Novo administrador';
    form.nome.readOnly = !!u;
    form.senha.required = !u;
    $('#ajuda-senha-administrador').textContent = u ? 'Deixe em branco para manter a senha atual (mínimo de 8 caracteres).' : 'Pelo menos 8 caracteres.';
    if (u) {
        form.nome.value = u.nome;
        form.grupo.value = u.grupo;
        form.comentario.value = u.comentario;
    } else {
        form.grupo.value = 'painel';
        form.senha.value = gerarSenha(10);
    }
    atualizarAjudaGrupo();
    $('#janela-administrador').showModal();
    (u ? form.senha : form.nome).focus();
}

$('#novo-administrador').addEventListener('click', () => abrirAdministrador(null));
$('#gerar-senha-administrador').addEventListener('click', () => { $('#form-administrador').senha.value = gerarSenha(10); });
$('#form-administrador').grupo.addEventListener('change', atualizarAjudaGrupo);

$('#form-administrador').addEventListener('submit', async (evento) => {
    evento.preventDefault();
    const form = evento.target;
    const u = estado.editandoAdministrador;
    await comBotao(form.querySelector('[type=submit]'), async () => {
        try {
            if (u) {
                const dados = { grupo: form.grupo.value, comentario: form.comentario.value.trim() };
                if (form.senha.value) dados.senha = form.senha.value;
                await api('PATCH', '/api/administradores/' + encodeURIComponent(u.id), dados);
                aviso('Administrador ' + u.nome + ' alterado.');
            } else {
                const dados = { nome: form.nome.value.trim(), senha: form.senha.value, grupo: form.grupo.value, comentario: form.comentario.value.trim() };
                await api('POST', '/api/administradores', dados);
                aviso(`Administrador ${dados.nome} cadastrado. Senha: ${dados.senha}`);
            }
            $('#janela-administrador').close();
            await carregarAdministradores();
        } catch (e) { mostrarErroForm(form, e.message); }
    });
});

async function alternarAdministrador(u) {
    if (!u.desativado && !await confirmar('Desativar administrador', `Desativar "${u.nome}"? Ele não conseguirá mais entrar no painel nem no MikroTik.`, 'Desativar')) return;
    try {
        await api('PATCH', '/api/administradores/' + encodeURIComponent(u.id), { desativado: !u.desativado });
        aviso(u.nome + (u.desativado ? ' ativado.' : ' desativado.'));
        await carregarAdministradores();
    } catch (e) { aviso(e.message, true); }
}

async function excluirAdministrador(u) {
    if (!await confirmar('Excluir administrador', `Excluir o usuário "${u.nome}" do MikroTik? Isso não pode ser desfeito.`, 'Excluir')) return;
    try {
        await api('DELETE', '/api/administradores/' + encodeURIComponent(u.id));
        aviso('Administrador ' + u.nome + ' excluído.');
        await carregarAdministradores();
    } catch (e) { aviso(e.message, true); }
}

// ------------------------------------------------------------------ configurações: escola e MikroTik

function recarregarLogos() {
    estado.versaoLogo = Date.now();
    document.querySelectorAll('[data-logo]').forEach((img) => { img.src = '/logo?v=' + estado.versaoLogo; });
}

function mostrarEscola(e) {
    const form = $('#form-escola');
    form.nome.value = e.nome;
    form.cidade.value = e.cidade;
    $('#logo-padrao').hidden = !e.logo_proprio;
    estado.info.escola = e.nome;
    estado.info.cidade = e.cidade;
    const texto = e.nome + (e.cidade ? ' · ' + e.cidade : '');
    document.querySelectorAll('[data-escola]').forEach((x) => { x.textContent = texto; });
}

function mostrarConexao(c) {
    const form = $('#form-mikrotik');
    form.ip.value = c.ip === c.padrao && !c.porta ? '' : c.ip;
    form.porta.value = c.porta || '';
    $('#estado-mikrotik').textContent = c.em_uso
        ? `Conectado por ${c.conexao} em ${c.em_uso}.`
        : `Sem resposta do MikroTik em ${c.ip}${c.porta ? ':' + c.porta : ''}.`;
}

async function carregarEscolaEConexao() {
    const [escola, conexao] = await Promise.all([api('GET', '/api/configuracoes/escola'), api('GET', '/api/configuracoes/mikrotik')]);
    mostrarEscola(escola);
    mostrarConexao(conexao);
}

$('#form-escola').addEventListener('submit', async (evento) => {
    evento.preventDefault();
    const form = evento.target;
    await comBotao(form.querySelector('[type=submit]'), async () => {
        try {
            mostrarEscola(await api('PUT', '/api/configuracoes/escola', { nome: form.nome.value, cidade: form.cidade.value }));
            aviso('Dados da escola salvos.');
        } catch (e) { aviso(e.message, true); }
    });
});

$('#arquivo-logo').addEventListener('change', async (evento) => {
    const arquivo = evento.target.files[0];
    evento.target.value = '';
    if (!arquivo) return;
    const dados = new FormData();
    dados.append('arquivo', arquivo);
    try {
        mostrarEscola(await api('POST', '/api/configuracoes/logo', dados));
        recarregarLogos();
        aviso('Logotipo trocado.');
    } catch (e) { aviso(e.message, true); }
});

$('#logo-padrao').addEventListener('click', async () => {
    if (!await confirmar('Logotipo', 'Voltar ao logotipo padrão do painel?', 'Voltar ao padrão')) return;
    try {
        mostrarEscola(await api('DELETE', '/api/configuracoes/logo'));
        recarregarLogos();
        aviso('Logotipo padrão de volta.');
    } catch (e) { aviso(e.message, true); }
});

$('#form-mikrotik').addEventListener('submit', async (evento) => {
    evento.preventDefault();
    const form = evento.target;
    const ip = form.ip.value.trim();
    const porta = form.porta.value ? parseInt(form.porta.value, 10) : null;
    const destino = (ip || '192.168.88.1') + (porta ? ':' + porta : '');
    if (!await confirmar('Conexão com o MikroTik', `Testar e passar a usar o MikroTik em ${destino}?`, 'Testar e salvar')) return;
    await comBotao(form.querySelector('[type=submit]'), async () => {
        try {
            const r = await api('PUT', '/api/configuracoes/mikrotik', { ip, porta });
            mostrarConexao(r);
            aviso(`Conectado ao MikroTik ${r.identidade} em ${r.em_uso}.`);
        } catch (e) { aviso(e.message, true); }
    });
});

// ------------------------------------------------------------------ visitantes

estado.visitantes = [];
estado.visitantesCriados = [];
estado.visitantesSelecionados = new Set();

function validoAte(iso) {
    const d = new Date(iso);
    const hoje = new Date();
    const hora = d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
    return d.toDateString() === hoje.toDateString() ? 'hoje, ' + hora
        : d.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' }) + ' ' + hora;
}

estado.qrWifi = '';

function cartaoVisitante(v) {
    return { usuario: v.usuario, senha: v.senha,
        comentario: 'Visitante · válido até ' + validoAte(v.ate) + (v.descricao ? ' · ' + v.descricao : ''),
        qr_wifi: estado.qrWifi, qr_login: v.qr_login };
}

async function carregarVisitantes() {
    const [lista, , wifi] = await Promise.all([api('GET', '/api/visitantes'), carregarPerfis(), api('GET', '/api/configuracoes/wifi')]);
    estado.visitantes = lista;
    estado.qrWifi = wifi.qr || '';
    const select = $('#perfil-visitantes');
    const atual = select.value || lembrado('perfil-visitante') || '';
    select.replaceChildren(...estado.perfis.map((p) => el('option', { value: p, texto: p })));
    if (estado.perfis.includes(atual)) select.value = atual;

    const ids = new Set(lista.map((v) => v.id));
    for (const id of [...estado.visitantesSelecionados]) if (!ids.has(id)) estado.visitantesSelecionados.delete(id);
    $('#encerrar-todos-visitantes').disabled = lista.length === 0;
    $('#imprimir-visitantes').disabled = !lista.some((v) => !v.expirado);

    const corpo = $('#lista-visitantes');
    corpo.replaceChildren();
    if (!lista.length) linhaVazia(corpo, 7, 'Nenhum visitante com senha válida.');
    for (const v of lista) {
        const situacao = v.expirado
            ? el('span', { class: 'etiqueta bloqueado', texto: 'Expirado' })
            : v.conectado ? el('span', { class: 'etiqueta ok', texto: 'Conectado' }) : el('span', { class: 'etiqueta off', texto: 'Válido' });
        corpo.append(el('tr', { class: v.expirado ? 'inativo' : '' },
            el('td', { class: 'col-check' }, el('input', {
                type: 'checkbox', checked: estado.visitantesSelecionados.has(v.id), 'aria-label': 'Selecionar ' + v.usuario,
                onchange: (e) => { e.target.checked ? estado.visitantesSelecionados.add(v.id) : estado.visitantesSelecionados.delete(v.id); atualizarSelecaoVisitantes(); },
            })),
            el('td', {}, el('strong', { class: 'mono', texto: v.usuario })),
            el('td', { 'data-rotulo': 'Senha', class: 'mono', texto: v.senha }),
            el('td', { 'data-rotulo': 'Descrição', texto: v.descricao || '—' }),
            el('td', { 'data-rotulo': 'Válido até', texto: validoAte(v.ate) }),
            el('td', {}, situacao, v.agendado ? null : el('span', { class: 'etiqueta alerta-amarelo', title: 'Sem agendamento no MikroTik: encerre manualmente', texto: ' sem agendamento' })),
            el('td', {}, el('div', { class: 'acoes' },
                el('button', { class: 'botao pequeno cor-roxo', type: 'button', texto: 'Imprimir', onclick: () => imprimir([cartaoVisitante(v)]) }),
                el('button', { class: 'botao pequeno cor-vermelho', type: 'button', texto: 'Encerrar agora', onclick: () => encerrarVisitante(v) }))),
        ));
    }
    atualizarSelecaoVisitantes();
}

// Mesmo tratamento do painel: minúsculas sem acento, só letras, até 10.
function prefixoVisitante(texto) {
    const letras = (texto || '').normalize('NFKD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/[^a-z]/g, '').slice(0, 10);
    return letras || 'visita';
}

$('#form-visitantes').nome.addEventListener('input', (e) => {
    const p = prefixoVisitante(e.target.value);
    $('#exemplo-nome-visitante').textContent = `Fica ${p}1, ${p}2…`;
});

$('#form-visitantes').addEventListener('submit', async (evento) => {
    evento.preventDefault();
    const form = evento.target;
    const validade = form.validade.value;
    const dados = {
        quantidade: parseInt(form.quantidade.value, 10) || 1,
        minutos: validade === 'fim' ? null : parseInt(validade, 10),
        ate_fim_do_dia: validade === 'fim',
        perfil: form.perfil.value,
        descricao: form.descricao.value.trim(),
        nome: form.nome.value.trim(),
    };
    lembrar('perfil-visitante', dados.perfil);
    await comBotao(form.querySelector('[type=submit]'), async () => {
        try {
            const r = await api('POST', '/api/visitantes', dados);
            estado.visitantesCriados = r.criados;
            $('#visitantes-criados').hidden = false;
            $('#resumo-visitantes-criados').textContent = `${r.criados.length} senha(s) válida(s) até ${validoAte(r.criados[0].ate)}.`;
            $('#lista-visitantes-criados').replaceChildren(...r.criados.map((c) =>
                el('li', {},
                    c.qr_login ? el('img', { src: c.qr_login, alt: 'QR code do login de ' + c.usuario, class: 'qr-miniatura' }) : null,
                    el('span', {}, 'Usuário ', el('b', { class: 'mono', texto: c.usuario }), '  ·  Senha ', el('b', { class: 'mono', texto: c.senha })))));
            aviso(`${r.criados.length} senha(s) de visitante criada(s).`);
            await carregarVisitantes();
        } catch (e) { aviso(e.message, true); }
    });
});

function atualizarSelecaoVisitantes() {
    const n = estado.visitantesSelecionados.size;
    $('#barra-selecao-visitantes').hidden = n === 0;
    $('#qtd-visitantes-selecionados').textContent = n === 1 ? '1 selecionado' : n + ' selecionados';
    const todos = $('#marcar-todos-visitantes');
    todos.checked = estado.visitantes.length > 0 && n === estado.visitantes.length;
    todos.indeterminate = n > 0 && n < estado.visitantes.length;
}

async function encerrarVarios(corpo, texto) {
    if (!await confirmar('Encerrar visitantes', texto, 'Encerrar')) return;
    try {
        const r = await api('POST', '/api/visitantes/encerrar', corpo);
        estado.visitantesSelecionados.clear();
        aviso(`${r.encerrados.length} visitante(s) encerrado(s).` + (r.erros.length ? ' Erros: ' + r.erros.join('; ') : ''), r.erros.length > 0);
        await carregarVisitantes();
    } catch (e) { aviso(e.message, true); }
}

$('#marcar-todos-visitantes').addEventListener('change', (e) => {
    estado.visitantesSelecionados = new Set(e.target.checked ? estado.visitantes.map((v) => v.id) : []);
    document.querySelectorAll('#lista-visitantes input[type=checkbox]').forEach((c) => { c.checked = e.target.checked; });
    atualizarSelecaoVisitantes();
});
$('#limpar-selecao-visitantes').addEventListener('click', () => {
    estado.visitantesSelecionados.clear();
    document.querySelectorAll('#lista-visitantes input[type=checkbox]').forEach((c) => { c.checked = false; });
    atualizarSelecaoVisitantes();
});
$('#imprimir-visitantes-selecionados').addEventListener('click', () =>
    imprimir(estado.visitantes.filter((v) => estado.visitantesSelecionados.has(v.id)).map(cartaoVisitante)));
$('#encerrar-visitantes-selecionados').addEventListener('click', () => {
    const ids = [...estado.visitantesSelecionados];
    encerrarVarios({ ids }, `Encerrar ${ids.length} visitante(s) selecionado(s)? Quem estiver conectado é desconectado.`);
});
$('#encerrar-todos-visitantes').addEventListener('click', () =>
    encerrarVarios({ todos: true }, `Encerrar TODAS as ${estado.visitantes.length} senha(s) de visitante? Quem estiver conectado é desconectado.`));
$('#fechar-visitantes-criados').addEventListener('click', () => {
    $('#visitantes-criados').hidden = true;
    estado.visitantesCriados = [];
});

$('#imprimir-visitantes-criados').addEventListener('click', () => imprimir(estado.visitantesCriados.map(cartaoVisitante)));
$('#imprimir-visitantes').addEventListener('click', () => imprimir(estado.visitantes.filter((v) => !v.expirado).map(cartaoVisitante)));

async function encerrarVisitante(v) {
    if (!await confirmar('Encerrar visitante', `Encerrar agora a senha ${v.usuario}? Se estiver conectado, é desconectado.`, 'Encerrar')) return;
    try {
        await api('DELETE', '/api/visitantes/' + encodeURIComponent(v.id));
        aviso(v.usuario + ' encerrado.');
        await carregarVisitantes();
    } catch (e) { aviso(e.message, true); }
}

// ------------------------------------------------------------------ configurações: Wi-Fi dos QR codes

function mostrarWifi(w) {
    const form = $('#form-wifi');
    form.ssid.value = w.ssid;
    form.seguranca.value = w.seguranca;
    form.senha.value = w.senha;
    $('#campo-senha-wifi').hidden = w.seguranca !== 'wpa';
    const previa = $('#previa-qr-wifi');
    previa.hidden = !w.qr;
    if (w.qr) previa.src = w.qr;
}

$('#form-wifi').seguranca.addEventListener('change', (e) => { $('#campo-senha-wifi').hidden = e.target.value !== 'wpa'; });
$('#form-wifi').addEventListener('submit', async (evento) => {
    evento.preventDefault();
    const form = evento.target;
    await comBotao(form.querySelector('[type=submit]'), async () => {
        try {
            const w = await api('PUT', '/api/configuracoes/wifi', { ssid: form.ssid.value.trim(), seguranca: form.seguranca.value, senha: form.senha.value });
            mostrarWifi(w);
            estado.qrWifi = w.qr || '';
            aviso(w.ssid ? 'Rede Wi-Fi dos QR codes salva.' : 'QR code do Wi-Fi desligado.');
        } catch (e) { aviso(e.message, true); }
    });
});

// ------------------------------------------------------------------ rede Alunos

// Hora do MikroTik (AAAA-MM-DDTHH:MM) dita em relação a "agora" do próprio roteador.
function quandoRelativo(iso, agoraIso) {
    if (!iso) return '';
    const dia = iso.slice(0, 10);
    const hora = iso.slice(11, 16).replace(':', 'h');
    const hoje = new Date(agoraIso.slice(0, 10) + 'T12:00');
    const alvo = new Date(dia + 'T12:00');
    const dias = Math.round((alvo - hoje) / 86400000);
    if (dias === 0) return 'às ' + hora;
    if (dias === 1) return 'amanhã às ' + hora;
    const semana = alvo.toLocaleDateString('pt-BR', { weekday: 'long' });
    return (dias < 7 ? semana : alvo.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' })) + ' às ' + hora;
}

const DIAS_SEMANA = ['dom', 'seg', 'ter', 'qua', 'qui', 'sex', 'sáb'];
estado.redeAlunos = null;
estado.alunosEditando = false;  // a atualização automática não apaga o que está sendo editado

function renderRedeAlunos(e) {
    estado.redeAlunos = e;
    const etiqueta = $('#etiqueta-rede-alunos');
    const texto = $('#estado-rede-alunos');
    $('#modo-rede-alunos').hidden = !e.configurado;
    $('#acoes-rede-alunos').hidden = !e.configurado || e.modo !== 'horario';
    if (!estado.alunosEditando) preencherConfigAlunos(e);
    if (!e.configurado) {
        etiqueta.className = 'etiqueta alerta-amarelo';
        etiqueta.textContent = 'Não configurada';
        texto.textContent = e.erro || 'Escolha a interface e os horários abaixo e salve.';
        return;
    }
    document.querySelectorAll('[data-modo]').forEach((b) => {
        b.classList.toggle('ativo', b.dataset.modo === e.modo);
        b.setAttribute('aria-checked', b.dataset.modo === e.modo ? 'true' : 'false');
    });
    etiqueta.className = 'etiqueta ' + (e.aberta ? 'ok' : 'off');
    etiqueta.textContent = e.aberta ? 'Aberta' : 'Fechada';
    const abre = quandoRelativo(e.abre_em, e.agora);
    const fecha = quandoRelativo(e.fecha_em, e.agora);
    texto.textContent = {
        liberado: `Liberada pelo painel. Fecha ${fecha}.`,
        fechado: `Fechada pelo painel até o fim deste horário.` + (abre ? ` Abre de novo ${abre}.` : ''),
        horario: `Aberta pelo horário. Fecha ${fecha}.`,
        fora: 'Fechada (fora do horário).' + (abre ? ` Abre ${abre}.` : ''),
        fixo: e.aberta ? 'Sempre aberta (horários desligados).' : 'Sempre fechada (horários desligados).',
    }[e.motivo] || '';
    $('#fechar-rede-alunos').hidden = !e.aberta;
    $('#horario-rede-alunos').hidden = !(e.motivo === 'liberado' || e.motivo === 'fechado');
}

// ---- interface e horários (editáveis)

function linhaHorario(j) {
    const tr = el('tr', {},
        el('td', { 'data-rotulo': 'Início' }, el('input', { type: 'time', value: j.inicio, required: true, class: 'hora-inicio', 'aria-label': 'Início' })),
        el('td', { 'data-rotulo': 'Fim' }, el('input', { type: 'time', value: j.fim, required: true, class: 'hora-fim', 'aria-label': 'Fim' })),
        el('td', { 'data-rotulo': 'Dias' }, el('div', { class: 'dias' },
            ...DIAS_SEMANA.map((nome, n) => el('label', {},
                el('input', { type: 'checkbox', value: String(n), checked: j.dias.includes(n) }), ' ' + nome)))),
        el('td', {}, el('button', { class: 'botao pequeno cor-vermelho', type: 'button', texto: 'Excluir',
            onclick: () => { tr.remove(); estado.alunosEditando = true; atualizarHorariosVazios(); } })));
    return tr;
}

function atualizarHorariosVazios() {
    const corpo = $('#lista-horarios-alunos');
    const vazio = corpo.querySelector('.vazio-horarios');
    const temLinhas = corpo.querySelector('tr:not(.vazio-horarios)');
    if (!temLinhas && !vazio) {
        corpo.append(el('tr', { class: 'vazio-horarios' }, el('td', { colspan: 4, class: 'vazio', texto: 'Nenhum horário: a rede só abre quando liberada pelo painel.' })));
    } else if (temLinhas && vazio) {
        vazio.remove();
    }
}

async function preencherConfigAlunos(e) {
    const corpo = $('#lista-horarios-alunos');
    corpo.replaceChildren(...e.janelas.map(linhaHorario));
    atualizarHorariosVazios();
    const select = $('#interface-rede-alunos');
    if (!estado.interfacesAlunos) {
        try { estado.interfacesAlunos = await api('GET', '/api/rede-alunos/interfaces'); } catch (erro) { estado.interfacesAlunos = []; }
    }
    const lista = estado.interfacesAlunos;
    const opcoes = lista.map((i) => el('option', { value: i.nome, disabled: i.protegida && i.nome !== e.interface,
        texto: `${i.nome} (${i.tipo}${i.desativada ? ', desligada' : ''}${i.protegida ? ', internet/painel: não pode' : ''})` }));
    if (!lista.some((i) => i.nome === e.interface)) opcoes.unshift(el('option', { value: e.interface, texto: e.interface + ' (não existe)' }));
    select.replaceChildren(...opcoes);
    select.value = e.interface;
}

$('#form-config-alunos').addEventListener('input', () => { estado.alunosEditando = true; });
$('#form-config-alunos').addEventListener('change', () => { estado.alunosEditando = true; });

$('#adicionar-horario-alunos').addEventListener('click', () => {
    estado.alunosEditando = true;
    const nova = linhaHorario({ inicio: '07:00', fim: '08:00', dias: [1, 2, 3, 4, 5] });
    $('#lista-horarios-alunos').append(nova);
    atualizarHorariosVazios();
    nova.querySelector('input').focus();
});

$('#desfazer-config-alunos').addEventListener('click', () => {
    estado.alunosEditando = false;
    if (estado.redeAlunos) preencherConfigAlunos(estado.redeAlunos);
});

$('#form-config-alunos').addEventListener('submit', async (evento) => {
    evento.preventDefault();
    const form = evento.target;
    const janelas = [...$('#lista-horarios-alunos').querySelectorAll('tr:not(.vazio-horarios)')].map((tr) => ({
        inicio: tr.querySelector('.hora-inicio').value,
        fim: tr.querySelector('.hora-fim').value,
        dias: [...tr.querySelectorAll('.dias input:checked')].map((c) => Number(c.value)),
    }));
    await comBotao(form.querySelector('[type=submit]'), async () => {
        try {
            const e = await api('PUT', '/api/rede-alunos/config', { interface: form.interface.value, janelas });
            estado.alunosEditando = false;
            estado.interfacesAlunos = null;
            renderRedeAlunos(e);
            aviso('Interface e horários da rede Alunos salvos.');
        } catch (erro) { aviso(erro.message, true); }
    });
});

document.querySelectorAll('[data-modo]').forEach((b) => b.addEventListener('click', async () => {
    const modo = b.dataset.modo;
    if (estado.redeAlunos && estado.redeAlunos.modo === modo) return;
    const textos = {
        horario: 'Voltar a abrir e fechar a rede Alunos pelos horários?',
        aberta: 'Deixar a rede Alunos sempre aberta (os horários param de valer)?',
        fechada: 'Deixar a rede Alunos sempre fechada? Os alunos conectados ficam sem internet agora.',
    };
    const nome = b.querySelector('strong').textContent;
    if (!await confirmar('Modo da rede Alunos', textos[modo], nome)) return;
    await comBotao(b, async () => {
        try {
            const e = await api('PUT', '/api/rede-alunos/modo', { modo });
            estado.interfacesAlunos = null;  // a interface pode ter ligado ou desligado
            renderRedeAlunos(e);
            aviso('Rede Alunos: ' + nome.toLowerCase() + '.');
        } catch (erro) { aviso(erro.message, true); }
    });
}));

async function carregarRedeAlunos() {
    try {
        renderRedeAlunos(await api('GET', '/api/rede-alunos'));
    } catch (e) {
        $('#estado-rede-alunos').textContent = 'Não foi possível ler: ' + e.message;
    }
}

async function acaoRedeAlunos(botao, caminho, corpo, mensagem) {
    await comBotao(botao, async () => {
        try {
            renderRedeAlunos(await api('POST', caminho, corpo));
            aviso(mensagem);
        } catch (e) { aviso(e.message, true); }
    });
}

$('#liberar-rede-alunos').addEventListener('click', (evento) => {
    const minutos = Number($('#minutos-rede-alunos').value);
    acaoRedeAlunos(evento.currentTarget, '/api/rede-alunos/liberar', { minutos }, 'Rede Alunos liberada.');
});
$('#fechar-rede-alunos').addEventListener('click', async (evento) => {
    const botao = evento.currentTarget;
    if (!await confirmar('Fechar a rede Alunos', 'Os alunos conectados ficam sem internet agora. Fechar?', 'Fechar agora')) return;
    acaoRedeAlunos(botao, '/api/rede-alunos/fechar', undefined, 'Rede Alunos fechada.');
});
$('#horario-rede-alunos').addEventListener('click', (evento) =>
    acaoRedeAlunos(evento.currentTarget, '/api/rede-alunos/horario', undefined, 'Rede Alunos de volta ao horário normal.'));

// ------------------------------------------------------------------ registro das abas

Object.assign(CARREGAR, {
    perfis: carregarPerfisDetalhes,
    sites: carregarSites,
    relatorio: carregarRelatorio,
    aviso: carregarAviso,
    historico: carregarHistorico,
    backup: carregarBackups,
    config: async () => {
        await carregarEscolaEConexao();
        await carregarConfig();
        mostrarWifi(await api('GET', '/api/configuracoes/wifi'));
    },
    visitantes: carregarVisitantes,
    alunos: carregarRedeAlunos,
    administradores: carregarAdministradores,
    rede: carregarRedeToda,
});
