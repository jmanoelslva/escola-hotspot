'use strict';
// Histórico de uso da internet (Início) e relatório mensal (Sistema → Relatório).
// Usa as funções de app.js ($, el, api, aviso, comBotao...).

const SVG_USO = 'http://www.w3.org/2000/svg';
estado.periodoUso = 'dia';

function svg(tag, atributos, ...filhos) {
    const elemento = document.createElementNS(SVG_USO, tag);
    for (const [chave, valor] of Object.entries(atributos || {})) elemento.setAttribute(chave, valor);
    for (const filho of filhos) if (filho) elemento.append(filho);
    return elemento;
}

function numeroBr(valor, casas) {
    return Number(valor).toLocaleString('pt-BR', { minimumFractionDigits: casas, maximumFractionDigits: casas });
}

function rotuloTempo(quando, periodo) {
    if (periodo === 'dia') return quando.slice(11, 16);
    if (periodo === '7d') return quando.slice(8, 10) + '/' + quando.slice(5, 7) + ' ' + quando.slice(11, 13) + 'h';
    return quando.slice(8, 10) + '/' + quando.slice(5, 7);
}

// Gráfico simples em SVG: linhas (Mbps) ou barras (GB por dia).
function graficoUso(dados, largura = 1000, altura = 220) {
    const pontos = dados.pontos;
    const margem = { esquerda: 46, direita: 8, topo: 12, baixo: 26 };
    const w = largura - margem.esquerda - margem.direita;
    const h = altura - margem.topo - margem.baixo;
    const maximo = Math.max(1, ...pontos.map((p) => Math.max(p.baixa, p.envia)));
    const y = (v) => margem.topo + h - (v / maximo) * h;
    const grafico = svg('svg', { viewBox: `0 0 ${largura} ${altura}`, class: 'grafico-uso', role: 'img' });
    for (let i = 0; i <= 4; i++) {
        const valor = (maximo / 4) * i;
        grafico.append(svg('line', { x1: margem.esquerda, x2: largura - margem.direita, y1: y(valor), y2: y(valor), class: 'grade' }),
            svg('text', { x: margem.esquerda - 6, y: y(valor) + 4, class: 'eixo', 'text-anchor': 'end' }, numeroBr(valor, valor < 10 ? 1 : 0)));
    }
    const passo = w / Math.max(pontos.length, 1);
    const x = (i) => margem.esquerda + passo * i + passo / 2;
    if (dados.unidade === 'GB') {
        const barra = Math.max(2, passo * 0.38);
        pontos.forEach((p, i) => {
            const titulo = svg('title', {}, `${rotuloTempo(p.quando, dados.periodo)}: ${numeroBr(p.baixa, 2)} GB baixados, ${numeroBr(p.envia, 2)} GB enviados, até ${p.sessoes} logados`);
            grafico.append(svg('g', {}, titulo,
                svg('rect', { x: x(i) - barra, y: y(p.baixa), width: barra, height: margem.topo + h - y(p.baixa), class: 'barra-baixa' }),
                svg('rect', { x: x(i), y: y(p.envia), width: barra, height: margem.topo + h - y(p.envia), class: 'barra-envia' })));
        });
    } else {
        const linha = (campo) => pontos.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(p[campo]).toFixed(1)}`).join(' ');
        if (pontos.length) {
            grafico.append(svg('path', { d: linha('baixa'), class: 'linha-baixa' }), svg('path', { d: linha('envia'), class: 'linha-envia' }));
        }
    }
    const marcas = Math.min(pontos.length, dados.periodo === 'dia' ? 8 : 7);
    for (let k = 0; k < marcas; k++) {
        const i = Math.round((k * (pontos.length - 1)) / Math.max(marcas - 1, 1));
        grafico.append(svg('text', { x: x(i), y: altura - 6, class: 'eixo', 'text-anchor': 'middle' }, rotuloTempo(pontos[i].quando, dados.periodo)));
    }
    return grafico;
}

async function carregarUso() {
    const area = $('#grafico-uso');
    try {
        const dados = await api('GET', '/api/uso?periodo=' + estado.periodoUso);
        document.querySelectorAll('[data-periodo]').forEach((b) => b.classList.toggle('ativo', b.dataset.periodo === estado.periodoUso));
        if (!dados.pontos.length) {
            area.replaceChildren(el('p', { class: 'dica', texto: dados.servico
                ? 'Ainda não há dados neste período. O painel registra o uso a cada 5 minutos.'
                : 'Para registrar o uso, um administrador full precisa ativar o serviço do painel em Sistema → Configurações.' }));
            $('#resumo-uso').textContent = '';
            return;
        }
        area.replaceChildren(graficoUso(dados));
        const picoSessoes = Math.max(...dados.pontos.map((p) => p.sessoes));
        const picoAparelhos = Math.max(...dados.pontos.map((p) => p.aparelhos));
        const total = dados.unidade === 'GB'
            ? ` · ${numeroBr(dados.pontos.reduce((s, p) => s + p.baixa, 0), 1)} GB baixados`
            : ` · pico de ${numeroBr(Math.max(...dados.pontos.map((p) => p.baixa)), 1)} Mbps`;
        $('#resumo-uso').textContent = `Até ${picoSessoes} logados ao mesmo tempo · até ${picoAparelhos} aparelhos na rede${total}`;
    } catch (e) {
        area.replaceChildren(el('p', { class: 'dica', texto: 'Não foi possível ler o histórico: ' + e.message }));
    }
}

document.querySelectorAll('[data-periodo]').forEach((b) => b.addEventListener('click', () => {
    estado.periodoUso = b.dataset.periodo;
    carregarUso();
}));

// ------------------------------------------------------------------ relatório mensal

function gb(bytes) {
    return numeroBr(bytes / 1e9, 2) + ' GB';
}

function linhaTabela(...celulas) {
    return el('tr', {}, ...celulas.map((c) => el('td', { texto: String(c) })));
}

function montarRelatorio(r) {
    const [ano, mes] = r.mes.split('-');
    const nomeMes = new Date(Number(ano), Number(mes) - 1, 1).toLocaleDateString('pt-BR', { month: 'long', year: 'numeric' });
    const uso = r.uso;
    const blocos = [
        el('div', { class: 'relatorio-topo' },
            el('img', { src: '/logo?v=' + (estado.versaoLogo || 0), alt: '' }),
            el('div', {}, el('h2', { texto: 'Relatório do Wi-Fi – ' + nomeMes }),
                el('div', { class: 'dica', texto: r.escola + (r.cidade ? ' · ' + r.cidade : '') }))),
        el('div', { class: 'cartoes-resumo' },
            cartaoNumero('Internet baixada', numeroBr(uso.baixado_gb, 1) + ' GB'),
            cartaoNumero('Internet enviada', numeroBr(uso.enviado_gb, 1) + ' GB'),
            cartaoNumero('Pico de logados', uso.pico_sessoes ? `${uso.pico_sessoes.valor} (${uso.pico_sessoes.quando.slice(8, 10)}/${mes} ${uso.pico_sessoes.quando.slice(11, 16)})` : '—'),
            cartaoNumero('Pico de aparelhos', uso.pico_aparelhos ? String(uso.pico_aparelhos.valor) : '—'),
            cartaoNumero('Visitantes criados', String(r.visitantes_criados)),
            cartaoNumero('Usuários cadastrados', String(r.usuarios))),
    ];
    if (uso.dias.length) {
        blocos.push(el('h3', { texto: 'Uso da internet por dia' }),
            graficoUso({ unidade: 'GB', periodo: '30d', pontos: uso.dias.map((d) => ({ quando: d.dia, baixa: d.baixado_gb, envia: d.enviado_gb, sessoes: d.sessoes })) }, 1000, 200),
            el('p', { class: 'dica legenda-uso' }, el('span', { class: 'cor-baixa' }), ' Baixado  ', el('span', { class: 'cor-envia' }), ' Enviado'));
    } else {
        blocos.push(el('p', { class: 'dica', texto: r.servico ? 'Sem registros de uso neste mês.' : 'Uso por dia indisponível: o serviço do painel não estava ativo.' }));
    }
    blocos.push(el('h3', { texto: 'O que foi feito no painel' }),
        el('table', { class: 'tabela tabela-relatorio' }, el('tbody', {},
            linhaTabela('Usuários cadastrados um a um', r.acoes.usuarios_criados),
            linhaTabela('Importações de planilha', r.acoes.importados),
            linhaTabela('Senhas novas geradas', r.acoes.senhas_novas),
            linhaTabela('Senhas trocadas pelos próprios usuários (Wi-Fi)', r.acoes.trocas_pelo_wifi),
            linhaTabela('Sites bloqueados no mês', r.acoes.sites_bloqueados),
            linhaTabela('Liberações da rede Alunos fora do horário', r.acoes.liberacoes_alunos),
            linhaTabela('Sites bloqueados em vigor', r.sites_bloqueados))));
    const desde = r.consumo_desde ? ` (desde ${dataHora(r.consumo_desde)})` : ' (desde o último "Zerar contadores")';
    blocos.push(el('h3', { texto: 'Consumo por turma' + desde }),
        el('table', { class: 'tabela tabela-relatorio' },
            el('thead', {}, el('tr', {}, el('th', { texto: 'Turma' }), el('th', { texto: 'Usuários' }), el('th', { texto: 'Consumo' }))),
            el('tbody', {}, ...r.turmas.map((t) => linhaTabela(t.turma, t.usuarios, gb(t.bytes))))),
        el('h3', { texto: 'Quem mais usou' + desde }),
        el('table', { class: 'tabela tabela-relatorio' },
            el('thead', {}, el('tr', {}, el('th', { texto: 'Usuário' }), el('th', { texto: 'Nome / turma' }), el('th', { texto: 'Consumo' }))),
            el('tbody', {}, ...r.maiores.map((u) => linhaTabela(u.nome, u.comentario, gb(u.bytes))))),
        el('p', { class: 'dica', texto: 'Gerado pelo Painel do Hotspot em ' + new Date().toLocaleString('pt-BR') + '.' }));
    return el('div', { class: 'relatorio' }, ...blocos);
}

async function gerarRelatorio() {
    const mes = $('#mes-relatorio').value;
    const area = $('#area-relatorio');
    area.replaceChildren(el('p', { class: 'dica', texto: 'Gerando…' }));
    try {
        estado.relatorioMensal = await api('GET', '/api/relatorio-mensal?mes=' + encodeURIComponent(mes));
        area.replaceChildren(montarRelatorio(estado.relatorioMensal));
        $('#imprimir-relatorio').disabled = false;
    } catch (e) {
        area.replaceChildren(el('p', { class: 'dica', texto: e.message }));
    }
}

async function carregarMensal() {
    const campo = $('#mes-relatorio');
    if (!campo.value) {
        const hoje = new Date();
        campo.value = `${hoje.getFullYear()}-${String(hoje.getMonth() + 1).padStart(2, '0')}`;
    }
    await gerarRelatorio();
}

$('#gerar-relatorio').addEventListener('click', (e) => comBotao(e.target, gerarRelatorio));
$('#mes-relatorio').addEventListener('change', () => { if ($('#mes-relatorio').value) gerarRelatorio(); });
$('#imprimir-relatorio').addEventListener('click', async () => {
    if (!estado.relatorioMensal) return;
    const area = $('#impressao');
    area.classList.add('modo-relatorio');
    area.replaceChildren(montarRelatorio(estado.relatorioMensal));
    await imagensProntas(area);
    await new Promise((pronto) => setTimeout(pronto, 100));
    window.print();
    area.classList.remove('modo-relatorio');
});

CARREGAR.mensal = carregarMensal;
