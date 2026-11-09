const f=t=>t?new Date(t*1000).toLocaleString("es-AR"):"—";
const esc=s=>String(s??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
fetch("/api/admin/stats").then(r=>r.json()).then(d=>{
 if(d.error){document.body.innerHTML="<p style='padding:30px'>"+esc(d.error)+"</p>";return}
 const c=d.cuentas,k=[["Cuentas",c.cuentas],["Verificadas",c.verificadas],["Activas (7 días)",c.activas_7d],["Con resumen diario",c.con_resumen_diario],
  ["Búsquedas en caché",d.cache.busquedas.archivos],["Detalles en caché",d.cache.detalles.archivos]];
 kpi.innerHTML=k.map(([a,b])=>`<div class="k"><b>${esc(b)}</b>${esc(a)}</div>`).join("");
 const ps=Object.entries(d.portales).sort((a,b)=>b[1].seguidas-a[1].seguidas);
 por.innerHTML=ps.length?ps.map(([n,p])=>`<tr><td>${esc(n)}</td><td class="${p.seguidas>=3?"mal":p.seguidas?"":"bien"}">${p.seguidas>=3?"CAÍDO ("+p.seguidas+" seguidas)":p.seguidas?"con fallas":"ok"}</td><td>${p.ok}</td><td>${p.fail}</td><td>${f(p.last_ok)}</td><td>${esc(p.last_note||"")}</td></tr>`).join(""):"<tr><td colspan=6>Todavía no hay consultas reales.</td></tr>";
 altas.innerHTML=c.altas_por_dia.map(([a,b])=>`<tr><td>${esc(a)}</td><td>${b}</td></tr>`).join("")||"<tr><td>Sin altas</td></tr>";
 const bk=d.backup;
 srv.textContent=(bk.activo?`Copia de seguridad: ${bk.ok===false?"FALLA ("+bk.error+")":bk.ultima?"ok, última "+f(bk.ultima)+" ("+bk.archivos+" archivos, cada "+bk.cada_min+" min"+(bk.cifrado?", cifrada":"")+")":"activa, esperando la primera copia"}${bk.restaurado?" · restauró "+bk.restaurado+" archivos al arrancar":""} · `:"Copia de seguridad: NO configurada · ")+`Modo público: ${d.publico?"sí":"no"} · Correo (Brevo): ${d.mail?"configurado":"NO configurado"} · Admins con alertas: ${d.admins} · Caché ${d.cache.ttl_min} min · ${d.cache.busquedas.kb+d.cache.detalles.kb} KB`;
});
