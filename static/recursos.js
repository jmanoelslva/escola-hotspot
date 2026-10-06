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

// ------------------------------------------------------------------ visitantes

estado.visitantes = [];
estado.visitantesCriados = [];

function validoAte(iso) {
    const d = new Date(iso);
    const hoje = new Date();
    const hora = d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
    return d.toDateString() === hoje.toDateString() ? 'hoje, ' + hora
        : d.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' }) + ' ' + hora;
}

function cartaoVisitante(v) {
    return { usuario: v.usuario, senha: v.senha,
        comentario: 'Visitante · válido até ' + validoAte(v.ate) + (v.descricao ? ' · ' + v.descricao : '') };
}

async function carregarVisitantes() {
    const [lista] = await Promise.all([api('GET', '/api/visitantes'), carregarPerfis()]);
    estado.visitantes = lista;
    const select = $('#perfil-visitantes');
    const atual = select.value || lembrado('perfil-visitante') || '';
    select.replaceChildren(...estado.perfis.map((p) => el('option', { value: p, texto: p })));
    if (estado.perfis.includes(atual)) select.value = atual;

    const corpo = $('#lista-visitantes');
    corpo.replaceChildren();
    if (!lista.length) linhaVazia(corpo, 6, 'Nenhum visitante com senha válida.');
    for (const v of lista) {
        const situacao = v.expirado
            ? el('span', { class: 'etiqueta bloqueado', texto: 'Expirado' })
            : v.conectado ? el('span', { class: 'etiqueta ok', texto: 'Conectado' }) : el('span', { class: 'etiqueta off', texto: 'Válido' });
        corpo.append(el('tr', { class: v.expirado ? 'inativo' : '' },
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
}

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
    };
    lembrar('perfil-visitante', dados.perfil);
    await comBotao(form.querySelector('[type=submit]'), async () => {
        try {
            const r = await api('POST', '/api/visitantes', dados);
            estado.visitantesCriados = r.criados;
            $('#visitantes-criados').hidden = false;
            $('#resumo-visitantes-criados').textContent = `${r.criados.length} senha(s) válida(s) até ${validoAte(r.criados[0].ate)}.`;
            $('#lista-visitantes-criados').replaceChildren(...r.criados.map((c) =>
                el('li', {}, el('span', { texto: 'Usuário ' }), el('b', { class: 'mono', texto: c.usuario }),
                    el('span', { texto: '  ·  Senha ' }), el('b', { class: 'mono', texto: c.senha }))));
            aviso(`${r.criados.length} senha(s) de visitante criada(s).`);
            await carregarVisitantes();
        } catch (e) { aviso(e.message, true); }
    });
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

// ------------------------------------------------------------------ configurações: páginas do hotspot

const NOMES_SITUACAO = { igual: ['Igual', 'ok'], diferente: ['Diferente', 'alerta-amarelo'], falta: ['Falta no roteador', 'bloqueado'], desconhecido: ['Sem tamanho', 'off'] };

function tamanhoArquivo(n) {
    return n === null || n === undefined ? '—' : bytes(n);
}

async function carregarPaginas() {
    const corpo = $('#lista-paginas');
    let r;
    try {
        r = await api('GET', '/api/paginas');
    } catch (e) {
        corpo.replaceChildren();
        linhaVazia(corpo, 4, e.message);
        $('#resumo-paginas').textContent = '';
        return;
    }
    $('#pastas-paginas').textContent = `Neste computador: ${r.pasta_local}  →  no roteador: ${r.pasta_roteador}/`;
    corpo.replaceChildren();
    const ordem = { falta: 0, diferente: 1, desconhecido: 2, igual: 3 };
    for (const a of r.arquivos.sort((x, y) => ordem[x.situacao] - ordem[y.situacao] || x.arquivo.localeCompare(y.arquivo))) {
        const [texto, classe] = NOMES_SITUACAO[a.situacao] || [a.situacao, 'off'];
        corpo.append(el('tr', {},
            el('td', {}, el('span', { class: 'mono', texto: a.arquivo })),
            el('td', { 'data-rotulo': 'Neste computador', texto: tamanhoArquivo(a.tamanho_painel) }),
            el('td', { 'data-rotulo': 'No roteador', texto: tamanhoArquivo(a.tamanho_roteador) }),
            el('td', {}, el('span', { class: 'etiqueta ' + classe, texto }))));
    }
    const pendentes = r.arquivos.filter((a) => a.situacao !== 'igual').length;
    $('#resumo-paginas').textContent = pendentes
        ? `${pendentes} de ${r.arquivos.length} arquivo(s) para enviar.`
        : `Os ${r.arquivos.length} arquivos estão iguais no roteador.`;
    $('#enviar-paginas').disabled = pendentes === 0;
}

async function enviarPaginas(todos, botao) {
    const texto = todos
        ? 'Enviar TODOS os arquivos das páginas para o roteador, substituindo os que estão lá?'
        : 'Enviar para o roteador os arquivos diferentes ou que faltam?';
    if (!await confirmar('Enviar páginas do hotspot', texto, 'Enviar')) return;
    await comBotao(botao, async () => {
        try {
            const r = await api('POST', '/api/paginas/enviar', { todos });
            if (r.erros.length) aviso(`${r.enviados.length} enviado(s). Erros: ${r.erros.join('; ')}`, true);
            else aviso(r.enviados.length ? `${r.enviados.length} arquivo(s) enviado(s) ao roteador.` : 'Nada para enviar.');
            await carregarPaginas();
        } catch (e) { aviso(e.message, true); }
    });
}

$('#comparar-paginas').addEventListener('click', (e) => comBotao(e.target, carregarPaginas));
$('#enviar-paginas').addEventListener('click', (e) => enviarPaginas(false, e.target));
$('#enviar-todas-paginas').addEventListener('click', (e) => enviarPaginas(true, e.target));

// ------------------------------------------------------------------ registro das abas

Object.assign(CARREGAR, {
    perfis: carregarPerfisDetalhes,
    sites: carregarSites,
    relatorio: carregarRelatorio,
    aviso: carregarAviso,
    historico: carregarHistorico,
    backup: carregarBackups,
    config: () => Promise.all([carregarConfig(), carregarPaginas()]),
    visitantes: carregarVisitantes,
});
