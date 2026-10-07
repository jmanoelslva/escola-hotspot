'use strict';
// Aba "Painel geral": saúde do roteador, gráfico ao vivo das interfaces e
// aviso de atualização do RouterOS. Usa as funções de app.js.

const PONTOS = 150;            // 150 leituras x 2 s = 5 minutos no gráfico
const INTERVALO_TRAFEGO = 2000;
const INTERVALO_SISTEMA = 10000;

estado.sistema = null;
estado.historico = {};         // nome da interface -> [{entrada, saida}]
estado.relogioTrafego = null;
estado.relogioSistema = null;

function mbps(bps) {
    if (bps >= 1e9) return (bps / 1e9).toFixed(2).replace('.', ',') + ' Gbps';
    if (bps >= 1e6) return (bps / 1e6).toFixed(1).replace('.', ',') + ' Mbps';
    return Math.round(bps / 1e3) + ' kbps';
}

function interfacesEscolhidas() {
    try {
        const salvas = JSON.parse(localStorage.getItem('painel.interfaces') || 'null');
        if (Array.isArray(salvas)) return salvas;
    } catch (e) { /* sem armazenamento */ }
    // Padrão: a interface de internet e as bridges (rede do hotspot).
    const s = estado.sistema;
    if (!s) return [];
    const padrao = s.interfaces.filter((i) => i.ligada && (i.nome === s.internet || i.tipo === 'bridge')).map((i) => i.nome);
    return padrao.length ? padrao.slice(0, 4) : s.interfaces.filter((i) => i.ligada).slice(0, 2).map((i) => i.nome);
}

function salvarEscolha(nomes) {
    try { localStorage.setItem('painel.interfaces', JSON.stringify(nomes)); } catch (e) { /* ignora */ }
}

// ------------------------------------------------------------------ cartões de saúde

function cartao(rotulo, valor, detalhe, classe) {
    return el('div', { class: 'cartao-numero ' + (classe || '') },
        el('span', { texto: rotulo }), el('strong', { texto: valor }), detalhe ? el('small', { texto: detalhe }) : null);
}

// Sessões do hotspot contra o limite da licença: amarelo a partir de 80%, vermelho a partir de 95%.
function cartaoSessoes(s) {
    if (!s.limite_hotspot) return cartao('Conectados agora', String(s.conectados), `${s.usuarios} usuário(s) cadastrado(s)`);
    const uso = s.conectados / s.limite_hotspot;
    const classe = uso >= 0.95 ? 'alerta-numero' : uso >= 0.8 ? 'atencao-numero' : '';
    return cartao('Sessões do hotspot', `${s.conectados} de ${s.limite_hotspot}`,
        `licença nível ${s.nivel || '?'} · ${s.usuarios} usuário(s) cadastrado(s)`, classe);
}

function renderSistema() {
    const s = estado.sistema;
    const memoria = s.memoria_total ? Math.round(s.memoria_usada / s.memoria_total * 100) : 0;
    const quente = s.temperatura !== null && s.temperatura >= 70;
    $('#cartoes-sistema').replaceChildren(
        cartao('CPU', s.cpu + '%', null, s.cpu >= 80 ? 'alerta-numero' : ''),
        cartao('Memória', memoria + '%', `${bytes(s.memoria_usada)} de ${bytes(s.memoria_total)}`, memoria >= 90 ? 'alerta-numero' : ''),
        cartao('Temperatura', s.temperatura === null ? '—' : String(s.temperatura).replace('.', ',') + ' °C', null, quente ? 'alerta-numero' : ''),
        cartao('Ligado há', tempo(s.uptime) || '—'),
        cartaoSessoes(s),
        cartao('Roteador', s.modelo || 'MikroTik', 'RouterOS ' + s.versao),
    );
}

function renderEscolhaInterfaces() {
    const escolhidas = new Set(interfacesEscolhidas());
    const lista = $('#lista-interfaces');
    lista.replaceChildren(...estado.sistema.interfaces.map((i) => el('label', { class: 'linha-check' + (i.ligada ? '' : ' desligada') },
        el('input', {
            type: 'checkbox', checked: escolhidas.has(i.nome),
            onchange: (e) => {
                const atual = new Set(interfacesEscolhidas());
                e.target.checked ? atual.add(i.nome) : atual.delete(i.nome);
                salvarEscolha([...atual].slice(0, 8));
                montarGraficos();
                lerTrafego();
            },
        }),
        `${i.nome}${i.comentario ? ' (' + i.comentario + ')' : ''}${i.nome === estado.sistema.internet ? ' · internet' : ''}${i.ligada ? '' : ' · desligada'}`)));
}

// ------------------------------------------------------------------ gráficos

const SVG = 'http://www.w3.org/2000/svg';

function montarGraficos() {
    const area = $('#graficos');
    const nomes = interfacesEscolhidas();
    area.replaceChildren();
    if (!nomes.length) {
        area.append(el('p', { class: 'dica', texto: 'Escolha acima as interfaces para acompanhar.' }));
        return;
    }
    for (const nome of nomes) {
        const info = estado.sistema.interfaces.find((i) => i.nome === nome) || { comentario: '' };
        const internet = nome === estado.sistema.internet;
        const svg = document.createElementNS(SVG, 'svg');
        svg.setAttribute('viewBox', `0 0 ${PONTOS - 1} 100`);
        svg.setAttribute('preserveAspectRatio', 'none');
        svg.setAttribute('class', 'grafico');
        svg.setAttribute('role', 'img');
        svg.setAttribute('aria-label', 'Tráfego de ' + nome);
        for (const y of [25, 50, 75]) {
            const linha = document.createElementNS(SVG, 'line');
            linha.setAttribute('x1', '0'); linha.setAttribute('x2', String(PONTOS - 1));
            linha.setAttribute('y1', String(y)); linha.setAttribute('y2', String(y));
            linha.setAttribute('class', 'grade-grafico');
            svg.append(linha);
        }
        for (const serie of ['entrada', 'saida']) {
            const area = document.createElementNS(SVG, 'path');
            area.setAttribute('class', 'area-' + serie);
            area.dataset.serie = serie;
            svg.append(area);
            const linha = document.createElementNS(SVG, 'polyline');
            linha.setAttribute('class', 'linha-' + serie);
            linha.dataset.serie = serie;
            svg.append(linha);
        }
        area.append(el('div', { class: 'cartao cartao-grafico', dados: { interface: nome } },
            el('div', { class: 'grafico-topo' },
                el('div', {},
                    el('strong', { texto: nome }),
                    internet ? el('span', { class: 'etiqueta bypass', texto: ' internet' }) : null,
                    info.comentario ? el('div', { class: 'ajuda', texto: info.comentario }) : null),
                el('div', { class: 'grafico-valores' },
                    el('span', { class: 'valor-entrada', title: internet ? 'Download da escola' : 'Entrando nesta interface' },
                        '↓ ', el('b', { dados: { valor: 'entrada' }, texto: '—' })),
                    el('span', { class: 'valor-saida', title: internet ? 'Upload da escola' : 'Saindo desta interface' },
                        '↑ ', el('b', { dados: { valor: 'saida' }, texto: '—' })))),
            el('div', { class: 'grafico-caixa' }, svg, el('span', { class: 'escala-grafico', dados: { escala: '1' } })),
            el('div', { class: 'grafico-legenda' },
                el('span', { class: 'legenda-entrada', texto: internet ? 'Download (entrada)' : 'Entrada' }),
                el('span', { class: 'legenda-saida', texto: internet ? 'Upload (saída)' : 'Saída' }),
                el('span', { class: 'ajuda', texto: 'últimos 5 minutos' })),
        ));
        desenhar(nome);
    }
}

function desenhar(nome) {
    const cartao = document.querySelector(`.cartao-grafico[data-interface="${CSS.escape(nome)}"]`);
    if (!cartao) return;
    const pontos = estado.historico[nome] || [];
    const maior = Math.max(1e6, ...pontos.map((p) => Math.max(p.entrada, p.saida))) * 1.15;
    const inicio = PONTOS - pontos.length;
    for (const serie of ['entrada', 'saida']) {
        const coords = pontos.map((p, i) => `${inicio + i},${(100 - p[serie] / maior * 100).toFixed(1)}`);
        cartao.querySelector(`polyline[data-serie="${serie}"]`).setAttribute('points', coords.join(' '));
        cartao.querySelector(`path[data-serie="${serie}"]`).setAttribute('d',
            coords.length ? `M${inicio},100 L${coords.join(' L')} L${PONTOS - 1},100 Z` : '');
    }
    const ultimo = pontos[pontos.length - 1];
    cartao.querySelector('[data-valor="entrada"]').textContent = ultimo ? mbps(ultimo.entrada) : '—';
    cartao.querySelector('[data-valor="saida"]').textContent = ultimo ? mbps(ultimo.saida) : '—';
    cartao.querySelector('[data-escala]').textContent = mbps(maior);
}

async function lerTrafego() {
    const nomes = interfacesEscolhidas();
    if (!nomes.length) return;
    try {
        const leituras = await api('GET', '/api/trafego?interfaces=' + encodeURIComponent(nomes.join(',')));
        for (const l of leituras) {
            const lista = estado.historico[l.nome] || (estado.historico[l.nome] = []);
            lista.push({ entrada: l.entrada_bps, saida: l.saida_bps });
            if (lista.length > PONTOS) lista.splice(0, lista.length - PONTOS);
            desenhar(l.nome);
        }
    } catch (e) {
        if (e.status !== 401) $('#erro-trafego').textContent = 'Não foi possível ler o tráfego: ' + e.message;
        return;
    }
    $('#erro-trafego').textContent = '';
}

async function lerSistema() {
    estado.sistema = await api('GET', '/api/sistema');
    renderSistema();
}

function pararGeral() {
    clearInterval(estado.relogioTrafego);
    clearInterval(estado.relogioSistema);
    estado.relogioTrafego = estado.relogioSistema = null;
}

// Só lê enquanto a aba está aberta e visível (não pesa no roteador à toa).
function seAbaGeral(funcao) {
    return () => {
        if (estado.abaAtual !== 'geral' || $('#tela-painel').hidden) { pararGeral(); return; }
        if (!document.hidden) funcao().catch(() => {});
    };
}

async function carregarGeral() {
    pararGeral();
    await lerSistema();
    renderEscolhaInterfaces();
    montarGraficos();
    lerTrafego();
    estado.relogioTrafego = setInterval(seAbaGeral(lerTrafego), INTERVALO_TRAFEGO);
    estado.relogioSistema = setInterval(seAbaGeral(lerSistema), INTERVALO_SISTEMA);
    mostrarAtualizacao(false);
}

// ------------------------------------------------------------------ atualização do RouterOS

function textoAtualizacao(a) {
    const partes = [];
    if (a.atualizacao_routeros) partes.push(`RouterOS ${a.disponivel} disponível (instalado: ${a.instalada}, canal ${a.canal}).`);
    if (a.atualizacao_firmware) partes.push(`Firmware da RouterBOARD ${a.firmware_novo} disponível (atual: ${a.firmware_atual}).`);
    return partes.join(' ');
}

async function mostrarAtualizacao(forcar) {
    let a;
    try {
        a = await api('GET', '/api/atualizacao' + (forcar ? '?forcar=true' : ''));
    } catch (e) {
        $('#estado-atualizacao').textContent = 'Não foi possível verificar: ' + e.message;
        return;
    }
    const tem = a.atualizacao_routeros || a.atualizacao_firmware;
    const faixa = $('#faixa-atualizacao');
    faixa.hidden = !tem;
    if (tem) $('#texto-faixa-atualizacao').textContent = textoAtualizacao(a);

    const quando = dataHora(a.verificado_em);
    let texto;
    if (a.falhou) texto = `Não foi possível consultar a MikroTik (${a.status || 'sem resposta'}). O roteador precisa de internet.`;
    else if (tem) texto = textoAtualizacao(a);
    else texto = `RouterOS ${a.instalada} (canal ${a.canal}) está atualizado.` + (a.firmware_atual ? ` Firmware ${a.firmware_atual}.` : '');
    $('#estado-atualizacao').textContent = texto + (quando ? ` Verificado em ${quando}.` : '');
    $('#como-atualizar').hidden = !tem;
}

$('#verificar-atualizacao').addEventListener('click', (e) => comBotao(e.target, () => mostrarAtualizacao(true)));
$('#fechar-faixa-atualizacao').addEventListener('click', () => { $('#faixa-atualizacao').hidden = true; });
$('#ver-atualizacao').addEventListener('click', () => abrirAba('geral'));

// Ao entrar no painel: consulta (o servidor guarda por 6 horas) e mostra a faixa no topo.
AO_ENTRAR.push(() => mostrarAtualizacao(false));

CARREGAR.geral = carregarGeral;
