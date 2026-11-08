'use strict';
const $ = id => document.getElementById(id);
const labels = {up: 'Disponível', warning: 'Atenção', down: 'Indisponível', pending: 'Sem dados'};
let services = [], selected = null, busy = false;
const date = value => new Date(value * 1000).toLocaleString('pt-BR');
function node(tag, text, className) { const el = document.createElement(tag); if (text !== undefined) el.textContent = text; if (className) el.className = className; return el; }
function badge(status) { return node('span', labels[status] || labels.pending, 'badge ' + status); }
function empty(tbody, columns, text) { const row = node('tr'), cell = node('td', text, 'empty'); cell.colSpan = columns; row.append(cell); tbody.append(row); }
function history() {
  const service = services.find(s => s.id === selected), rows = $('history-rows'), timeline = $('timeline');
  rows.replaceChildren(); timeline.replaceChildren();
  $('history-title').textContent = service ? service.name : 'Selecione um serviço';
  if (!service || !service.history.length) { $('history-description').textContent = 'Aguardando a primeira verificação deste serviço.'; empty(rows, 4, 'Ainda não há resultados.'); return; }
  const items = service.history;
  [...items].reverse().forEach(item => { const bar = node('span', '', item.status); bar.title = `${date(item.checked_at)} · ${labels[item.status]}`; timeline.append(bar); });
  $('history-description').textContent = `${items.length} verificações exibidas · sequência da mais antiga para a mais recente. A tabela mostra as 10 últimas.`;
  items.slice(0, 10).forEach(item => { const row = node('tr'); const status = node('td'); status.append(badge(item.status)); row.append(node('td', date(item.checked_at)), status, node('td', `${item.latency_ms.toFixed(1)} ms`, 'timing'), node('td', item.message)); rows.append(row); });
}
function render(data) {
  services = data.services;
  if (!services.some(s => s.id === selected)) selected = services[0]?.id || null;
  const counts = {up:0, warning:0, down:0};
  services.forEach(s => { if(s.latest) counts[s.latest.status]++; });
  $('count-total').textContent = services.length;
  Object.entries(counts).forEach(([key,value]) => $('count-' + key).textContent = value);
  const stamps = services.flatMap(s => s.latest ? [s.latest.checked_at] : []);
  $('last-check').textContent = stamps.length ? new Date(Math.max(...stamps) * 1000).toLocaleTimeString('pt-BR') : 'Aguardando';
  $('interval').textContent = `Intervalo de ${data.interval_seconds} s após cada rodada`;
  const stale = services.some(s => s.latest && data.server_time-s.latest.checked_at > data.interval_seconds + 90);
  const pending = services.filter(s => !s.latest).length;
  $('connection').textContent = data.collector_running ? 'Coletor em execução' : 'Coletor interrompido';
  $('connection').className = 'connection' + (data.collector_running ? '' : ' error');
  const warning = !data.collector_running ? 'A coleta foi interrompida. Os resultados abaixo podem estar desatualizados. Verifique os logs da aplicação.' : stale ? 'Há resultados antigos. Os estados abaixo representam a última verificação registrada.' : pending ? `${pending} serviço(s) aguardando a primeira verificação.` : '';
  $('notice').hidden = !warning; $('notice').textContent = warning;
  const rows = $('service-rows'); rows.replaceChildren();
  services.forEach(s => {
    const r = s.latest, row = node('tr'), name = node('td'), button = node('button', s.name, 'service-button');
    button.type='button'; button.setAttribute('aria-pressed', String(selected === s.id));
    button.addEventListener('click', () => {selected=s.id; render(data);});
    name.append(button, node('span', s.type.toUpperCase(), 'service-type'));
    const status=node('td'); status.append(badge(r?.status || 'pending'));
    const cert = r?.expires_at ? `${r.days_remaining} dias · ${new Date(r.expires_at).toLocaleDateString('pt-BR')}` : s.type==='tls' ? 'Sem validade confirmada' : 'Não se aplica';
    row.append(name,status,node('td',r ? `${r.latency_ms.toFixed(1)} ms` : '—','timing'),node('td',cert),node('td',r ? date(r.checked_at) : '—'));
    rows.append(row);
  });
  history();
}
async function refresh() {
  if(busy) return;
  busy=true; $('refresh').disabled=true;
  try {
    const response=await fetch('/api/snapshot',{cache:'no-store', signal:AbortSignal.timeout(5000)});
    if(!response.ok) throw new Error('snapshot indisponível');
    render(await response.json());
  } catch {
    $('connection').textContent='Painel sem conexão'; $('connection').className='connection error';
    $('notice').hidden=false; $('notice').textContent='Não foi possível atualizar o painel. Os dados já exibidos podem estar desatualizados. Tentaremos novamente em alguns segundos.';
  } finally {busy=false; $('refresh').disabled=false;}
}
$('refresh').addEventListener('click',refresh);
refresh(); setInterval(refresh,5000);
