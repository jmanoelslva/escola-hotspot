# Painel do Hotspot - OPCIONAL: ativa a REST API por HTTPS (www-ssl).
# Sem isto o painel funciona por HTTP (servico www). Com isto, a conexao fica criptografada.
#
# Como usar: Winbox > Files, arraste este arquivo; depois, no New Terminal:
#   /import mikrotik-https.rsc
#
# Cria uma CA propria (painel-ca) e, com ela, assina o certificado do www-ssl
# (painel-hotspot). Pode rodar de novo: refaz tudo se uma tentativa anterior
# ficou pela metade.

:if ([:len [/certificate find where name="painel-hotspot" and private-key]] = 0) do={
    :put "Criando os certificados (no hEX pode levar alguns segundos)..."
    /certificate remove [find where name="painel-hotspot" or name="painel-ca"]

    /certificate add name=painel-ca common-name=painel-ca days-valid=3650 key-usage=key-cert-sign,crl-sign
    /certificate sign painel-ca
    :local espera 0
    :while ([:len [/certificate find where name="painel-ca" and private-key]] = 0 && $espera < 120) do={
        :delay 1s
        :set espera ($espera + 1)
    }

    /certificate add name=painel-hotspot common-name=192.168.88.1 subject-alt-name=IP:192.168.88.1 days-valid=3650 key-usage=digital-signature,key-encipherment,tls-server
    /certificate sign painel-hotspot ca=painel-ca
    :set espera 0
    :while ([:len [/certificate find where name="painel-hotspot" and private-key]] = 0 && $espera < 120) do={
        :delay 1s
        :set espera ($espera + 1)
    }
}

:if ([:len [/certificate find where name="painel-hotspot" and private-key]] = 0) do={
    :error "O certificado painel-hotspot nao ficou pronto. Rode /import mikrotik-https.rsc de novo."
}

/ip service set www-ssl certificate=painel-hotspot disabled=no
:put "www-ssl ativo com o certificado painel-hotspot. O painel passa a usar HTTPS sozinho em ate 5 minutos."
