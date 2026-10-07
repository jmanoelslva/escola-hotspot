# Painel do Hotspot - redes da escola (RouterOS 7)
#
#   VLAN200-ADMINISTRATIVO  10.0.1.1/22 (era /24)  hotspot + IPv6 so depois do login
#   VLAN300-ALUNOS          10.1.0.1/21 (era /23)  aberta, IPv6, liga/desliga por horario
#   VLAN100-GERENCIA_AP     172.16.1.1/24          sem mudanca
#
# Como usar: Winbox > Files, arraste este arquivo; depois, no New Terminal:
#   /import mikrotik-redes.rsc
# Pode rodar de novo: cada parte confere o que ja existe.
# Regras criadas aqui tem comentario "painel-redes" (filtros) ou "painel-v6" (IPv6 por MAC).

# ---------------------------------------------------------------- 1. relogio
# Os horarios da rede Alunos dependem do relogio certo.
/system clock set time-zone-name=America/Maceio
:do { /system ntp client set enabled=yes servers=a.ntp.br,b.ntp.br } on-error={
    :do { /system ntp client servers add address=a.ntp.br } on-error={}
    :do { /system ntp client servers add address=b.ntp.br } on-error={}
    /system ntp client set enabled=yes
}

# ---------------------------------------------------------------- 2. enderecos e DHCP
# Administrativo: /22 (1.013 IPs para 50 professores + quem mais conectar), lease curto.
/ip address set [find interface="VLAN200-ADMINISTRATIVO" address="10.0.1.1/24"] address=10.0.1.1/22
/ip pool set [find name="ADMINISTRATIVO"] ranges=10.0.0.10-10.0.0.254,10.0.1.2-10.0.1.254,10.0.2.1-10.0.2.254,10.0.3.1-10.0.3.254
/ip dhcp-server set [find name="ADMINISTRATIVO"] lease-time=10m
:if ([:len [/ip dhcp-server network find address="10.0.1.0/24"]] > 0) do={
    /ip dhcp-server network set [find address="10.0.1.0/24"] address=10.0.0.0/22 gateway=10.0.1.1 dns-server=10.0.1.1
} else={
    :if ([:len [/ip dhcp-server network find address="10.0.0.0/22"]] = 0) do={
        /ip dhcp-server network add address=10.0.0.0/22 gateway=10.0.1.1 dns-server=10.0.1.1
    }
}

# Alunos: /21 (2.032 IPs para 600 alunos, inclusive celulares que trocam de MAC).
/ip address set [find interface="VLAN300-ALUNOS" address="10.1.0.1/23"] address=10.1.0.1/21
/ip pool set [find name="ALUNOS"] ranges=10.1.0.2-10.1.0.254,10.1.1.1-10.1.1.254,10.1.2.1-10.1.2.254,10.1.3.1-10.1.3.254,10.1.4.1-10.1.4.254,10.1.5.1-10.1.5.254,10.1.6.1-10.1.6.254,10.1.7.1-10.1.7.254
/ip dhcp-server set [find name="ALUNOS"] lease-time=15m
:if ([:len [/ip dhcp-server network find address="10.1.0.0/23"]] > 0) do={
    /ip dhcp-server network set [find address="10.1.0.0/23"] address=10.1.0.0/21 gateway=10.1.0.1 dns-server=10.1.0.1
} else={
    :if ([:len [/ip dhcp-server network find address="10.1.0.0/21"]] = 0) do={
        /ip dhcp-server network add address=10.1.0.0/21 gateway=10.1.0.1 dns-server=10.1.0.1
    }
}
/ip dns set allow-remote-requests=yes

# ---------------------------------------------------------------- 3. hotspot no Administrativo
# Perfil copiado do hsprof1 (mesmas paginas, dominio e login), com o endereco da VLAN 200.
# O hotspot de teste (ether3-TESTE) continua como esta.
:if ([:len [/ip hotspot profile find name="hsprof-adm"]] = 0) do={
    :do { /ip hotspot profile add name=hsprof-adm copy-from=hsprof1 hotspot-address=10.0.1.1 } on-error={
        :local p [/ip hotspot profile find name="hsprof1"]
        /ip hotspot profile add name=hsprof-adm hotspot-address=10.0.1.1 dns-name=[/ip hotspot profile get $p dns-name] html-directory=[/ip hotspot profile get $p html-directory] login-by=[/ip hotspot profile get $p login-by] http-cookie-lifetime=[/ip hotspot profile get $p http-cookie-lifetime]
    }
}
:if ([:len [/ip hotspot find interface="VLAN200-ADMINISTRATIVO"]] = 0) do={
    /ip hotspot add name=hotspot-adm interface=VLAN200-ADMINISTRATIVO profile=hsprof-adm address-pool=none idle-timeout=5m disabled=no
}

# ---------------------------------------------------------------- 4. firewall IPv4
/ip firewall address-list remove [find list="painel-redes-internas"]
/ip firewall address-list
add list=painel-redes-internas address=10.0.0.0/22 comment="painel-redes: administrativo"
add list=painel-redes-internas address=172.16.1.0/24 comment="painel-redes: gerencia dos APs"
add list=painel-redes-internas address=192.168.88.0/24 comment="painel-redes: rede do painel"
add list=painel-redes-internas address=192.168.130.0/24 comment="painel-redes: hotspot de teste"
add list=painel-redes-internas address=192.168.0.0/24 comment="painel-redes: rede do modem"
{
    /ip firewall filter remove [find comment~"^painel-redes"]
    :local antes [/ip firewall filter find dynamic=no]
    /ip firewall filter add chain=forward in-interface=VLAN300-ALUNOS dst-address-list=painel-redes-internas action=drop comment="painel-redes: alunos nao acessam as outras redes"
    /ip firewall filter add chain=forward in-interface=VLAN200-ADMINISTRATIVO dst-address=172.16.1.0/24 action=drop comment="painel-redes: administrativo nao acessa a gerencia dos APs"
    /ip firewall filter add chain=input in-interface=VLAN300-ALUNOS protocol=udp dst-port=53,67 action=accept comment="painel-redes: alunos usam DNS e DHCP do roteador"
    /ip firewall filter add chain=input in-interface=VLAN300-ALUNOS protocol=tcp dst-port=53 action=accept comment="painel-redes: alunos usam DNS do roteador"
    /ip firewall filter add chain=input in-interface=VLAN300-ALUNOS protocol=icmp action=accept comment="painel-redes: ping no roteador"
    /ip firewall filter add chain=input in-interface=VLAN300-ALUNOS action=drop comment="painel-redes: alunos nao acessam o roteador"
    :if ([:len $antes] > 0) do={ /ip firewall filter move [find comment~"^painel-redes"] destination=($antes->0) }
}

# ---------------------------------------------------------------- 5. IPv6
# Prefixo /56 da operadora: um /64 para o Administrativo e outro para os Alunos.
# Hoje o cliente DHCPv6 esta em ether1-WAN "searching" (atras do modem nao chega
# prefixo). Ao passar para o PPPoE, mova o cliente para pppoe-DAVINET mantendo
# pool-name=ipv6-operadora e rode este arquivo de novo.
/ipv6 dhcp-client set [find] pool-name=ipv6-operadora pool-prefix-length=64
:if ([:len [/interface list find name="painel-lan6"]] = 0) do={ /interface list add name=painel-lan6 comment="painel-redes" }
:foreach i in={"VLAN200-ADMINISTRATIVO";"VLAN300-ALUNOS"} do={
    :if ([:len [/interface list member find list="painel-lan6" interface=$i]] = 0) do={ /interface list member add list=painel-lan6 interface=$i }
    :if ([:len [/ipv6 address find interface=$i from-pool="ipv6-operadora"]] = 0) do={
        :do { /ipv6 address add interface=$i from-pool=ipv6-operadora address=::1/64 advertise=yes comment="painel-redes" } on-error={
            :put ("IPv6 de " . $i . ": o prefixo da operadora ainda nao chegou. Rode este arquivo de novo depois.")
        }
    }
}
/ipv6 nd set [find interface=all] advertise-dns=yes

{
    /ipv6 firewall filter remove [find comment~"^painel-redes"]
    :local antes [/ipv6 firewall filter find dynamic=no]
    /ipv6 firewall filter add chain=forward connection-state=established,related action=accept comment="painel-redes: respostas"
    /ipv6 firewall filter add chain=forward connection-state=invalid action=drop comment="painel-redes: pacotes invalidos"
    /ipv6 firewall filter add chain=forward in-interface=VLAN300-ALUNOS out-interface-list=painel-lan6 action=drop comment="painel-redes: alunos nao acessam o administrativo"
    /ipv6 firewall filter add chain=forward in-interface=VLAN300-ALUNOS action=accept comment="painel-redes: alunos saem para a internet"
    /ipv6 firewall filter add chain=forward in-interface=VLAN200-ADMINISTRATIVO action=jump jump-target=painel-hs-v6 comment="painel-redes: IPv6 so para quem fez login no hotspot"
    /ipv6 firewall filter add chain=forward in-interface=VLAN200-ADMINISTRATIVO action=reject reject-with=icmp-admin-prohibited comment="painel-redes: sem login, sem IPv6 (o aparelho usa o IPv4 e ve o login)"
    /ipv6 firewall filter add chain=forward connection-state=new out-interface-list=painel-lan6 action=drop comment="painel-redes: a internet nao abre conexao para dentro"
    /ipv6 firewall filter add chain=input in-interface-list=painel-lan6 protocol=icmpv6 action=accept comment="painel-redes: ICMPv6 (descoberta de vizinhos)"
    /ipv6 firewall filter add chain=input in-interface-list=painel-lan6 protocol=udp dst-port=53 action=accept comment="painel-redes: DNS do roteador"
    /ipv6 firewall filter add chain=input in-interface-list=painel-lan6 protocol=tcp dst-port=53 action=accept comment="painel-redes: DNS do roteador"
    /ipv6 firewall filter add chain=input in-interface=VLAN300-ALUNOS action=drop comment="painel-redes: alunos nao acessam o roteador"
    :if ([:len $antes] > 0) do={ /ipv6 firewall filter move [find comment~"^painel-redes"] destination=($antes->0) }
}

# IPv6 de quem entra e sai do hotspot: na hora (perfis de usuario) e conferido a cada minuto.
/ip hotspot user profile set [find] on-login=":local m \$\"mac-address\"; :if ([:len [/ipv6 firewall filter find chain=\"painel-hs-v6\" src-mac-address=\$m]] = 0) do={ /ipv6 firewall filter add chain=painel-hs-v6 src-mac-address=\$m action=accept comment=\"painel-v6\" }" on-logout="/ipv6 firewall filter remove [find chain=\"painel-hs-v6\" src-mac-address=\$\"mac-address\"]"
/system script remove [find name="painel-hs-v6"]
/system script add name=painel-hs-v6 policy=read,write,test comment="painel-redes" source="# IPv6 do Administrativo: libera o MAC de quem esta logado no hotspot ou\r\n# liberado (bypass) e fecha o de quem saiu. Roda a cada minuto (agendador\r\n# painel-hs-v6). Gerado pelo mikrotik-redes.rsc.\r\n:local quer [:toarray \"\"]\r\n:foreach a in=[/ip hotspot active find] do={\r\n    :set quer (\$quer, [/ip hotspot active get \$a mac-address])\r\n}\r\n:foreach b in=[/ip hotspot ip-binding find where type=\"bypassed\" and disabled=no] do={\r\n    :local mac [/ip hotspot ip-binding get \$b mac-address]\r\n    :if ([:len \$mac] > 0) do={ :set quer (\$quer, \$mac) }\r\n}\r\n:foreach r in=[/ipv6 firewall filter find chain=\"painel-hs-v6\"] do={\r\n    :if ([:typeof [:find \$quer [/ipv6 firewall filter get \$r src-mac-address]]] = \"nil\") do={\r\n        /ipv6 firewall filter remove \$r\r\n    }\r\n}\r\n:foreach mac in=\$quer do={\r\n    :if ([:len [/ipv6 firewall filter find chain=\"painel-hs-v6\" src-mac-address=\$mac]] = 0) do={\r\n        /ipv6 firewall filter add chain=painel-hs-v6 src-mac-address=\$mac action=accept comment=\"painel-v6\"\r\n    }\r\n}"
/system scheduler remove [find name="painel-hs-v6"]
/system scheduler add name=painel-hs-v6 interval=1m start-time=startup on-event="/system script run painel-hs-v6" policy=read,write,test comment="painel-redes: IPv6 do administrativo"

# ---------------------------------------------------------------- 6. horario da rede Alunos
# Seg a sex 08:50-09:10, 12:00-12:50, 14:40-15:00. Fora disso a VLAN300-ALUNOS fica
# desligada (sem gateway, DHCP e internet). O painel libera ou fecha na hora criando
# os agendadores painel-alunos-liberado / painel-alunos-fechado.
/system script remove [find name="painel-alunos"]
/system script add name=painel-alunos policy=read,write,test comment="painel-redes" source="# Rede Alunos: aberta nos horarios (segunda a sexta) ou quando o painel libera.\r\n# Roda a cada minuto (agendador painel-alunos). Gerado pelo mikrotik-redes.rsc.\r\n:local janelas {\"08:50-09:10\";\"12:00-12:50\";\"14:40-15:00\"}\r\n:local vlan \"VLAN300-ALUNOS\"\r\n:local d [/system clock get date]\r\n:local ano [:tonum [:pick \$d 0 4]]\r\n:local mes ([:tonum (\"1\" . [:pick \$d 5 7])] - 100)\r\n:local dia ([:tonum (\"1\" . [:pick \$d 8 10])] - 100)\r\n:local tab {0;3;2;5;0;3;5;1;4;6;2;4}\r\n:if (\$mes < 3) do={ :set ano (\$ano - 1) }\r\n:local semana ((\$ano + (\$ano / 4) - (\$ano / 100) + (\$ano / 400) + (\$tab->(\$mes - 1)) + \$dia) % 7)\r\n:local agora [:totime [/system clock get time]]\r\n:local aberta false\r\n:if ((\$semana >= 1) && (\$semana <= 5)) do={\r\n    :foreach j in=\$janelas do={\r\n        :local ini [:totime ([:pick \$j 0 5] . \":00\")]\r\n        :local fim [:totime ([:pick \$j 6 11] . \":00\")]\r\n        :if ((\$agora >= \$ini) && (\$agora < \$fim)) do={ :set aberta true }\r\n    }\r\n}\r\n:if ([:len [/system scheduler find name=\"painel-alunos-fechado\"]] > 0) do={ :set aberta false }\r\n:if ([:len [/system scheduler find name=\"painel-alunos-liberado\"]] > 0) do={ :set aberta true }\r\n:local desligada [/interface get [find name=\$vlan] disabled]\r\n:if (\$aberta && \$desligada) do={\r\n    /interface enable [find name=\$vlan]\r\n    :log info \"painel-alunos: rede Alunos aberta\"\r\n}\r\n:if ((!\$aberta) && (!\$desligada)) do={\r\n    /interface disable [find name=\$vlan]\r\n    :log info \"painel-alunos: rede Alunos fechada\"\r\n}"
/system scheduler remove [find name="painel-alunos"]
/system scheduler add name=painel-alunos interval=1m start-time=startup on-event="/system script run painel-alunos" policy=read,write,test comment="painel-redes: horario da rede Alunos"
/system script run painel-alunos

:put "Redes configuradas. Confira: /ip hotspot print, /ipv6 address print e /log print where message~\"painel\""

# ---------------------------------------------------------------- para desfazer (copie e cole se precisar)
# /system scheduler remove [find name~"^painel-(alunos|hs-v6)"]
# /system script remove [find name~"^painel-(alunos|hs-v6)"]
# /interface enable VLAN300-ALUNOS
# /ip firewall filter remove [find comment~"^painel-redes"]
# /ipv6 firewall filter remove [find comment~"^painel-redes" or chain="painel-hs-v6"]
# /ip hotspot remove [find name="hotspot-adm"]
# /ip hotspot user profile set [find] on-login="" on-logout=""
