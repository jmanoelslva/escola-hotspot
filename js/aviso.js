// Mostra o aviso da escola (aviso.txt, gravado pelo Painel do Hotspot) no
// elemento #aviso-escola. Sem arquivo ou com arquivo vazio, não mostra nada.
function carregarAviso() {
    var caixa = document.getElementById('aviso-escola');
    if (!caixa || !window.XMLHttpRequest) return;
    var pedido = new XMLHttpRequest();
    pedido.open('GET', 'aviso.txt?t=' + new Date().getTime(), true);
    pedido.onreadystatechange = function () {
        if (pedido.readyState !== 4 || pedido.status !== 200) return;
        var texto = (pedido.responseText || '').replace(/^\s+|\s+$/g, '');
        if (!texto || texto.charAt(0) === '<') return; // vazio, ou página de erro do roteador
        caixa.textContent = texto;
        caixa.hidden = false;
    };
    try { pedido.send(); } catch (e) { /* sem aviso */ }
}
