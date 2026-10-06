// Mostra o aviso da escola no elemento #aviso-escola.
// O Painel do Hotspot grava aviso-escola.js (var AVISO_ESCOLA = "...") na pasta
// do hotspot; a página carrega esse arquivo com <script>, como faz com o CSS.
// Sem o arquivo, ou com o texto vazio, não mostra nada.
function carregarAviso() {
    var caixa = document.getElementById('aviso-escola');
    if (!caixa) return;
    var texto = typeof AVISO_ESCOLA === 'string' ? AVISO_ESCOLA : '';
    texto = texto.replace(/^\s+|\s+$/g, '');
    if (!texto) return;
    caixa.textContent = texto;
    caixa.hidden = false;
}
