'use strict';
// Service worker do Painel do Hotspot: permite instalar como app.
// Sempre busca na rede primeiro (o painel só funciona com o MikroTik ao alcance);
// as telas guardadas só aparecem se o computador do painel estiver fora do ar.

const CACHE = 'painel-hotspot-v1';
const TELAS = ['/', '/static/style.css', '/static/app.js', '/static/recursos.js', '/static/logo.png', '/static/icone-192.png'];

self.addEventListener('install', (evento) => {
    evento.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(TELAS)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (evento) => {
    evento.waitUntil(caches.keys()
        .then((nomes) => Promise.all(nomes.filter((n) => n !== CACHE).map((n) => caches.delete(n))))
        .then(() => self.clients.claim()));
});

self.addEventListener('fetch', (evento) => {
    const pedido = evento.request;
    const url = new URL(pedido.url);
    // API, downloads e outros sites: sempre direto na rede, nunca do cache.
    if (pedido.method !== 'GET' || url.origin !== self.location.origin || url.pathname.startsWith('/api/')) return;
    evento.respondWith(
        fetch(pedido).then((resposta) => {
            if (resposta.ok && TELAS.includes(url.pathname)) {
                const copia = resposta.clone();
                caches.open(CACHE).then((cache) => cache.put(pedido, copia));
            }
            return resposta;
        }).catch(() => caches.match(pedido).then((guardada) => guardada || Response.error()))
    );
});
