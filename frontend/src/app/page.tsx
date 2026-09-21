'use client';

import {useEffect,useMemo,useState} from 'react';
import {
  LayoutDashboard,FileText,Users,Boxes,ReceiptText,RefreshCw,BarChart3,Settings,
  ShieldCheck,Building2,Plus,Trash2,CheckCircle2,Download,Menu,Search,Lock,
  Database,LogOut,Check,Clock,Send,UserCheck
} from 'lucide-react';

const API=process.env.NEXT_PUBLIC_API_URL||'http://localhost:8000';
const money=(n:number|string|undefined)=>'₹ '+Number(n||0).toLocaleString('en-IN',{minimumFractionDigits:2,maximumFractionDigits:2});
const today=()=>new Date().toISOString().slice(0,10);
const presets:any={
  REGULAR_5:{name:'5% Regular',scheme:'REGULAR',rate:5},REGULAR_12:{name:'12% Regular',scheme:'REGULAR',rate:12},
  REGULAR_18:{name:'18% Regular',scheme:'REGULAR',rate:18},REGULAR_28:{name:'28% Regular',scheme:'REGULAR',rate:28},
  COMPOSITION_1:{name:'1% Composition',scheme:'COMPOSITION',rate:1},COMPOSITION_5:{name:'5% Composition',scheme:'COMPOSITION',rate:5},
  COMPOSITION_6:{name:'6% Composition',scheme:'COMPOSITION',rate:6},EXEMPT:{name:'Exempt / Nil-rated',scheme:'REGULAR',rate:0}
};
type Line={id:string;product_id:string|null;description:string;hsn_sac:string;unit:string;qty:number;rate:number;gst_rate:number};

async function api(path:string,token:string|null,options:RequestInit={}) {
  const headers=new Headers(options.headers||{});
  if(!headers.has('Content-Type') && options.body) headers.set('Content-Type','application/json');
  if(token) headers.set('Authorization','Bearer '+token);
  const r=await fetch(API+path,{...options,headers});
  const text=await r.text();
  let data:any={}; try{data=text?JSON.parse(text):null}catch{data=text}
  if(!r.ok) throw new Error(data?.detail||data?.message||text||`Request failed (${r.status})`);
  return data;
}

export default function Home(){
  const [token,setToken]=useState<string|null>(null);
  const [user,setUser]=useState<any>(null);
  const [company,setCompany]=useState<any>(null);
  const [gstin,setGstin]=useState<any>(null);
  const [gstins,setGstins]=useState<any[]>([]);
  const [customers,setCustomers]=useState<any[]>([]);
  const [vendors,setVendors]=useState<any[]>([]);
  const [products,setProducts]=useState<any[]>([]);
  const [dashboard,setDashboard]=useState<any>(null);
  const [active,setActive]=useState('Dashboard');
  const [sidebar,setSidebar]=useState(true);
  const [scheme,setScheme]=useState('REGULAR');
  const [customerId,setCustomerId]=useState('');
  const [intra,setIntra]=useState(true);
  const [lines,setLines]=useState<Line[]>([]);
  const [period,setPeriod]=useState('2026-09');
  const [invoiceDate,setInvoiceDate]=useState(today());
  const [invoiceNumber,setInvoiceNumber]=useState('SDE/26-27/0001');
  const [savedId,setSavedId]=useState<string|null>(null);
  const [invoiceStatus,setInvoiceStatus]=useState<string|null>(null);
  const [irn,setIrn]=useState<any>(null);
  const [gstr1,setGstr1]=useState<any>(null);
  const [gstr3b,setGstr3b]=useState<any>(null);
  const [recon,setRecon]=useState<any>(null);
  const [message,setMessage]=useState('Ready');
  const [loginEmail,setLoginEmail]=useState('admin@gstpro.local');
  const [loginPassword,setLoginPassword]=useState('');
  const [loginError,setLoginError]=useState('');

  const permissions:string[]=user?.permissions||[];
  const can=(p:string)=>permissions.includes(p);
  const selectedCustomer=customers.find(c=>c.id===customerId)||customers[0];

  const totals=useMemo(()=>lines.reduce((a,l)=>{
    const t=l.qty*l.rate;
    const c=scheme==='COMPOSITION'?0:intra?t*l.gst_rate/200:0;
    const g=scheme==='COMPOSITION'?0:intra?0:t*l.gst_rate/100;
    return {...a,taxable:a.taxable+t,cgst:a.cgst+c,sgst:a.sgst+c,igst:a.igst+g,total:a.total+t+c+c+g};
  },{taxable:0,cgst:0,sgst:0,igst:0,total:0}),[lines,scheme,intra]);

  async function bootstrap(t:string){
    try{
      const me=await api('/api/auth/me',t);
      setUser(me);
      const companies=await api('/api/companies',t);
      const c=companies?.[0]||null;
      setCompany(c);
      if(c){
        const gs=await api('/api/gstins?company_id='+encodeURIComponent(c.id),t);
        setGstins(gs||[]);
        setGstin(gs?.[0]||null);
        const [p,cu,v]=await Promise.all([
          api('/api/products?company_id='+encodeURIComponent(c.id),t),
          api('/api/customers?company_id='+encodeURIComponent(c.id),t),
          api('/api/vendors?company_id='+encodeURIComponent(c.id),t)
        ]);
        setProducts(p||[]); setCustomers(cu||[]); setVendors(v||[]);
        setCustomerId(cu?.[0]?.id||'');
        await refreshDashboard(t,c.id);
      }
    }catch(e:any){setMessage(e.message||'Session initialization failed');logout();}
  }

  useEffect(()=>{
    const t=localStorage.getItem('gstpro_token');
    if(t){setToken(t);bootstrap(t);}
  },[]);

  async function refreshDashboard(t=token,cid=company?.id){
    if(!t||!cid)return;
    try{setDashboard(await api('/api/dashboard?period='+period+'&company_id='+encodeURIComponent(cid),t));}catch(e:any){setMessage(e.message);}
  }

  async function login(){
    try{
      setLoginError('');
      const j=await api('/api/auth/login',null,{method:'POST',body:JSON.stringify({email:loginEmail,password:loginPassword})});
      const u={...j.user,permissions:j.permissions||[]};
      localStorage.setItem('gstpro_token',j.access_token);
      localStorage.setItem('gstpro_user',JSON.stringify(u));
      setToken(j.access_token);setUser(u);setLoginPassword('');
      await bootstrap(j.access_token);
    }catch(e:any){setLoginError(e.message||'Login failed');}
  }

  function logout(){
    localStorage.removeItem('gstpro_token');localStorage.removeItem('gstpro_user');
    setToken(null);setUser(null);setCompany(null);setGstin(null);
  }

  function addLine(product?:any){
    const p=product||products[0];
    setLines(x=>[...x,{id:crypto.randomUUID(),product_id:p?.id||null,description:p?.description||'Custom Item',hsn_sac:p?.hsn_sac||'998313',unit:p?.unit||'NOS',qty:1,rate:Number(p?.rate||0),gst_rate:Number(p?.gst_rate||18)}]);
  }

  function updateLine(id:string,key:string,val:any){setLines(x=>x.map(l=>l.id===id?{...l,[key]:val}:l));}

  useEffect(()=>{if(token&&products.length&&!lines.length)addLine(products[0]);},[token,products.length]);

  function applyPreset(k:string){
    const p=presets[k];setScheme(p.scheme);setLines(x=>x.map(l=>({...l,gst_rate:p.rate})));setMessage(p.name+' applied to open lines');
  }

  async function saveInvoice(){
    if(!company||!gstin||!selectedCustomer){setMessage('Select company, GSTIN and customer first');return;}
    if(!can('create')){setMessage('Your role cannot create invoices');return;}
    try{
      const req={
        invoice_type:scheme==='COMPOSITION'?'BILL_OF_SUPPLY':'TAX_INVOICE',scheme,
        company_id:company.id,gstin_id:gstin.id,supplier_state_code:gstin.state_code,
        place_of_supply:selectedCustomer.state_code||gstin.state_code,supplier_gstin:gstin.gstin,
        customer_gstin:selectedCustomer.gstin||null,customer_name:selectedCustomer.name,
        invoice_date:invoiceDate,series:'SDE',invoice_number:invoiceNumber,
        lines:lines.map(l=>({...l,product_id:l.product_id||null})),reverse_charge:false
      };
      const row=await api('/api/invoices',token,{method:'POST',body:JSON.stringify(req)});
      setSavedId(row.id);setInvoiceStatus(row.status);setIrn(row.einvoice||null);setMessage('Draft saved');
      return row;
    }catch(e:any){setMessage(e.message);}
  }

  async function submitInvoice(){
    if(!savedId||!can('edit'))return;
    try{const row=await api('/api/invoices/'+savedId+'/submit',token,{method:'POST'});setInvoiceStatus('PENDING_APPROVAL');setMessage('Invoice submitted for approval');return row;}
    catch(e:any){setMessage(e.message);}
  }

  async function approveInvoice(decision:'APPROVE'|'REJECT'){
    if(!savedId||!can('approve'))return;
    try{
      const row=await api('/api/invoices/'+savedId+'/approve',token,{method:'POST',body:JSON.stringify({invoice_id:savedId,decision,comment:decision==='APPROVE'?'Approved from GST Pro':'Rejected from GST Pro'})});
      setInvoiceStatus(decision==='APPROVE'?'APPROVED':'REJECTED');setMessage('Invoice '+decision.toLowerCase()+'d');
      return row;
    }catch(e:any){setMessage(e.message);}
  }

  async function generateIrn(){
    const row=savedId?{id:savedId}:await saveInvoice();
    if(!row||!can('edit'))return;
    try{const j=await api('/api/einvoice/mock',token,{method:'POST',body:JSON.stringify({invoice_id:row.id})});setIrn(j);setInvoiceStatus('EINVOICE_GENERATED');setMessage('Mock IRN generated');}
    catch(e:any){setMessage(e.message);}
  }

  async function loadReturn(kind:string){
    if(!company)return;
    try{
      setMessage('Loading...');
      const qs='?period='+encodeURIComponent(period)+'&company_id='+encodeURIComponent(company.id);
      if(kind==='GSTR1')setGstr1(await api('/api/returns/gstr1/draft'+qs,token));
      if(kind==='GSTR3B')setGstr3b(await api('/api/returns/gstr3b/draft'+qs,token));
      if(kind==='RECON')setRecon(await api('/api/reconciliation'+qs,token));
      setMessage('Ready');
    }catch(e:any){setMessage(e.message);}
  }

  async function lockReturn(kind:string){
    if(!gstin||!can('lock')){setMessage('Your role cannot lock returns');return;}
    try{await api('/api/returns/lock',token,{method:'POST',body:JSON.stringify({gstin_id:gstin.id,return_type:kind,period})});setMessage(kind+' '+period+' locked for filing review');}
    catch(e:any){setMessage(e.message);}
  }

  async function download(path:string,filename:string){
    try{
      const headers:any={};if(token)headers.Authorization='Bearer '+token;
      const r=await fetch(API+path,{headers});if(!r.ok)throw new Error(await r.text());
      const blob=await r.blob();const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=filename;a.click();URL.revokeObjectURL(url);
    }catch(e:any){setMessage(e.message);}
  }

  const nav: Array<{name:string; icon:React.ElementType; permission:string}> = [
    {name:'Dashboard',icon:LayoutDashboard,permission:'read'},{name:'Invoices',icon:FileText,permission:'read'},
    {name:'Customers',icon:Users,permission:'read'},{name:'Vendors',icon:Users,permission:'read'},
    {name:'Products / Services',icon:Boxes,permission:'read'},{name:'GST Rate Presets',icon:ReceiptText,permission:'read'},
    {name:'E-Invoice',icon:ShieldCheck,permission:'read'},{name:'Returns (GSTR-1 / 3B)',icon:RefreshCw,permission:'read'},
    {name:'Reconciliation',icon:RefreshCw,permission:'read'},{name:'Reports',icon:BarChart3,permission:'read'},
    {name:'Masters',icon:Database,permission:'read'},{name:'Users & Roles',icon:Users,permission:'admin'},
    {name:'Company / GSTINs',icon:Building2,permission:'read'},{name:'Settings',icon:Settings,permission:'read'}
  ].filter(item=>can(item.permission));

  if(!token)return <Login email={loginEmail} password={loginPassword} setEmail={setLoginEmail} setPassword={setLoginPassword} error={loginError} login={login}/>;

  return <div className="app">
    {sidebar&&<aside className="sidebar">
      <div className="brand"><div className="logo">₹</div><div><b>GST Pro</b><small>Invoice · E-Invoice · Returns</small></div></div>
      <nav>{nav.map(item=>{const Icon=item.icon;return <button key={item.name} className={active===item.name?'nav active':'nav'} onClick={()=>setActive(item.name)}><Icon size={17}/>{item.name}</button>})}</nav>
      <div className="sidebarFoot">🇮🇳<span>Compliance Made Simple<br/>for Indian Businesses</span></div>
    </aside>}
    <main className="main">
      <header>
        <button className="iconBtn" onClick={()=>setSidebar(!sidebar)}><Menu size={19}/></button>
        <div className="crumb">GST Pro <span>/</span> {active}</div><div className="grow"/>
        <select className="company" value={gstin?.id||''} onChange={e=>setGstin(gstins.find(x=>x.id===e.target.value)||null)}>
          {gstins.map(g=><option key={g.id} value={g.id}>{company?.trade_name||company?.legal_name} · {g.gstin}</option>)}
        </select>
        <span className="fy">FY 2026–27</span><div className="avatar">{user?.name?.[0]||'A'}</div><b>{user?.name||'User'}</b>
        <button className="iconBtn" onClick={logout}><LogOut size={16}/></button>
      </header>

      {active==='Dashboard'&&<Dashboard data={dashboard} period={period} setPeriod={setPeriod} reload={()=>refreshDashboard()}/>}
      {active==='Invoices'&&<InvoiceWorkspace {...{lines,setLines,products,customers,customerId,setCustomerId,scheme,setScheme,intra,setIntra,totals,applyPreset,addLine,updateLine,saveInvoice,submitInvoice,approveInvoice,generateIrn,irn,message,savedId,invoiceStatus,invoiceDate,setInvoiceDate,invoiceNumber,setInvoiceNumber,can,download,token,gstinState:gstin?.state_code||'33',gstinNumber:gstin?.gstin||'',companyName:company?.trade_name||company?.legal_name||'',companyAddress:[company?.address?.city,company?.address?.state,company?.address?.pincode].filter(Boolean).join(', ')}}/>}
      {active==='Returns (GSTR-1 / 3B)'&&<Returns {...{period,setPeriod,gstr1,gstr3b,loadReturn,lockReturn,download,company}}/>}
      {active==='Reconciliation'&&<Reconciliation recon={recon} period={period} setPeriod={setPeriod} load={()=>loadReturn('RECON')}/>}
      {(active==='Customers'||active==='Vendors'||active==='Products / Services')&&<Masters active={active} products={products} customers={customers} vendors={vendors} reload={()=>bootstrap(token!)}/>}
      {active==='Company / GSTINs'&&<CompanyView company={company} gstins={gstins}/>}
      {active==='Users & Roles'&&<UsersView token={token} company={company} can={can}/>}
      {active==='Reports'&&<Reports period={period} company={company} download={download}/>}
      {active==='GST Rate Presets'&&<PresetView/>}
      {active==='E-Invoice'&&<EInvoiceView savedId={savedId} status={invoiceStatus} irn={irn}/>}
      {active==='Settings'&&<SettingsView user={user} company={company}/>}
      {active==='Masters'&&<CompanyView company={company} gstins={gstins}/>}
      <footer>GST Pro · Production-oriented GST workflow · <span>v1.0 foundation</span><span>{message}</span></footer>
    </main>
  </div>;
}

function Login(p:any){return <div className="loginPage"><div className="loginCard"><div className="logo big">₹</div><h1>GST Pro</h1><p>GST Invoice & Tax Compliance Platform</p><label>Email<input value={p.email} onChange={e=>p.setEmail(e.target.value)}/></label><label>Password<input type="password" value={p.password} onChange={e=>p.setPassword(e.target.value)} onKeyDown={e=>{if(e.key==='Enter')p.login()}}/></label>{p.error&&<div className="error">{p.error}</div>}<button className="primaryBtn wide" onClick={p.login}>Sign in</button><small>Use an account provisioned for this GST Pro company.</small></div></div>}

function Dashboard({data,period,setPeriod,reload}:any){return <><section className="top"><div><h1>Compliance Dashboard</h1><p>One view of sales, tax, ITC and filing readiness.</p></div><div className="status"><CheckCircle2 size={18}/> {data?.gstr1_status||'DRAFT'}</div></section><div className="dashGrid">{[['Invoices',data?.invoice_count||0],['Taxable Sales',money(data?.taxable_sales)],['Output Tax',money(data?.output_tax)],['ITC Available',money(data?.itc_available)],['Net Tax',money(data?.net_tax)],['AATO',money(data?.aato)]].map(([a,b])=><div className="metric" key={String(a)}><span>{a}</span><b>{b}</b></div>)}</div><div className="bottom"><div className="infoPanel"><h2>Compliance controls</h2><p>{data?.e_invoice_applicable?'✓ E-invoicing applicable at current AATO':'✓ E-invoicing threshold not reached'}</p><p>{data?.e_invoice_30day_rule?'⚠ 30-day IRP reporting rule active':'✓ 30-day rule not applicable at current AATO'}</p><p>✓ GSTR-1 / GSTR-3B remain draft-first</p><p>✓ Return periods can be locked before filing</p></div><div className="infoPanel"><h2>Period</h2><input value={period} onChange={e=>setPeriod(e.target.value)}/><button className="primaryBtn" onClick={reload}>Refresh dashboard</button></div></div></>}

function InvoiceWorkspace(p:any){
 return <><section className="top"><div><h1>Create Tax Invoice</h1><p>Automatic state-of-supply logic, tax calculation and maker-checker workflow.</p></div><div className="status">{p.invoiceStatus||'DRAFT'} · {p.message}</div></section>
 <div className="workspace"><section className="editor">
   <div className="tabs"><button className="selected">{p.scheme==='COMPOSITION'?'Bill of Supply':'Tax Invoice'}</button><div className="grow"/><b className="smallBadge">{p.scheme}</b></div>
   <div className="formGrid">
     <label>Customer *<select value={p.customerId} onChange={e=>{p.setCustomerId(e.target.value);const c=p.customers.find((x:any)=>x.id===e.target.value);if(c)p.setIntra(String(c.state_code)===String(p.gstinState))}}><option value="">Select customer</option>{p.customers.map((c:any)=><option value={c.id} key={c.id}>{c.name} · {c.gstin||'Unregistered'}</option>)}</select></label>
     <label>Invoice Date *<input type="date" value={p.invoiceDate} onChange={e=>p.setInvoiceDate(e.target.value)}/></label>
     <label>Invoice No. *<input value={p.invoiceNumber} onChange={e=>p.setInvoiceNumber(e.target.value)}/></label>
     <label>Place of Supply *<select value={p.intra?p.gstinState:(p.customers.find((c:any)=>c.id===p.customerId)?.state_code||'')} onChange={e=>p.setIntra(e.target.value===p.gstinState)}><option value={p.gstinState}>Supplier state ({p.gstinState})</option>{p.customers.find((c:any)=>c.id===p.customerId)?.state_code&&<option value={p.customers.find((c:any)=>c.id===p.customerId).state_code}>{p.customers.find((c:any)=>c.id===p.customerId).state_code}</option>}</select></label>
   </div>
   <div className="party"><div><b>{p.customers.find((c:any)=>c.id===p.customerId)?.name||'Select customer'}</b><span>GSTIN: {p.customers.find((c:any)=>c.id===p.customerId)?.gstin||'Unregistered'}</span><strong>Supplier State: {p.gstinState} · POS: {p.intra?p.gstinState:(p.customers.find((c:any)=>c.id===p.customerId)?.state_code||'')}</strong></div><div className="supply intra"><b>{p.scheme==='COMPOSITION'?'Composition Supply':p.intra?'Intra-State Supply':'Inter-State Supply'}</b><span>{p.scheme==='COMPOSITION'?'No GST charged to customer':p.intra?'CGST + SGST':'IGST'}</span></div></div>
   <div className="sectionTitle"><h2>Line Items</h2><div><button onClick={()=>p.addLine()}><Plus size={15}/> Add Item</button></div></div>
   <div className="tableWrap"><table><thead><tr><th>#</th><th>Item / Service</th><th>HSN/SAC</th><th>Unit</th><th>Qty *</th><th>Rate</th><th>GST %</th><th>Taxable</th><th>CGST</th><th>SGST</th><th>IGST</th><th>Total</th><th/></tr></thead><tbody>{p.lines.map((l:Line,i:number)=>{const t=l.qty*l.rate,c=p.scheme==='COMPOSITION'?0:p.intra?t*l.gst_rate/200:0,g=p.scheme==='COMPOSITION'?0:p.intra?0:t*l.gst_rate/100;return <tr key={l.id}><td>{i+1}</td><td><select value={l.product_id||''} onChange={e=>{const q=p.products.find((x:any)=>x.id===e.target.value);if(q){p.updateLine(l.id,'product_id',q.id);p.setLines(p.lines.map((x:Line)=>x.id===l.id?{...x,description:q.description,hsn_sac:q.hsn_sac,unit:q.unit,rate:q.rate,gst_rate:q.gst_rate}:x))}}}><option value="">Custom Entry</option>{p.products.map((q:any)=><option value={q.id} key={q.id}>{q.description}</option>)}</select></td><td><input value={l.hsn_sac} onChange={e=>p.updateLine(l.id,'hsn_sac',e.target.value)}/></td><td>{l.unit}</td><td><input className="edit" type="number" value={l.qty} onChange={e=>p.updateLine(l.id,'qty',+e.target.value)}/></td><td><input className="edit" type="number" value={l.rate} onChange={e=>p.updateLine(l.id,'rate',+e.target.value)}/></td><td><select value={l.gst_rate} onChange={e=>p.updateLine(l.id,'gst_rate',+e.target.value)}>{[0,5,12,18,28].map(x=><option value={x} key={x}>{x}</option>)}</select></td><td>{money(t)}</td><td>{money(c)}</td><td>{money(c)}</td><td>{money(g)}</td><td><b>{money(t+c+c+g)}</b></td><td><button className="delete" onClick={()=>p.setLines(p.lines.filter((x:Line)=>x.id!==l.id))}><Trash2 size={15}/></button></td></tr>})}</tbody></table></div>
   <div className="controls"><label>GST Rate Preset<select onChange={e=>p.applyPreset(e.target.value)}>{Object.entries(presets).map(([k,v]:any)=><option key={k} value={k}>{v.name}</option>)}</select></label><div className="totals"><div>Taxable <b>{money(p.totals.taxable)}</b></div><div>CGST <b>{money(p.totals.cgst)}</b></div><div>SGST <b>{money(p.totals.sgst)}</b></div><div>IGST <b>{money(p.totals.igst)}</b></div><div className="grand">Grand Total <b>{money(p.totals.total)}</b></div></div></div>
   <div className="actions">{p.can('create')&&<button onClick={p.saveInvoice}>Save Draft</button>}{p.savedId&&p.can('edit')&&p.invoiceStatus==='DRAFT'&&<button className="primary" onClick={p.submitInvoice}><Send size={14}/> Submit for Approval</button>}{p.savedId&&p.can('approve')&&p.invoiceStatus==='PENDING_APPROVAL'&&<><button className="success" onClick={()=>p.approveInvoice('APPROVE')}><Check size={14}/> Approve</button><button className="danger" onClick={()=>p.approveInvoice('REJECT')}>Reject</button></>}{p.savedId&&p.can('edit')&&p.invoiceStatus==='APPROVED'&&<button className="primary" onClick={p.generateIrn}><ShieldCheck size={14}/> Generate E-Invoice (Mock)</button>}{p.savedId&&<button onClick={()=>p.download('/api/invoices/'+p.savedId+'/pdf','invoice.pdf')}><Download size={14}/> PDF</button>}</div>
 </section><aside className="right"><div className="panel"><div className="panelHead"><h2>Maker-Checker</h2><span className="pill green">{p.invoiceStatus||'DRAFT'}</span></div><p><Clock size={14}/> Draft → Submit → CA/Approver → Approve → E-Invoice</p>{p.invoiceStatus==='PENDING_APPROVAL'&&<p><UserCheck size={14}/> Waiting for an approver with the required permission.</p>}</div><div className="panel preview"><div className="panelHead"><h2>Invoice Preview</h2></div><div className="paper"><b>{p.companyName||'Company'}</b><small>GSTIN: {p.gstinNumber||'—'}<br/>{p.companyAddress||''}</small><hr/><b>{p.scheme==='COMPOSITION'?'BILL OF SUPPLY':'TAX INVOICE'}</b>{p.lines.map((l:Line)=><p key={l.id}>{l.description} × {l.qty} — {money(l.qty*l.rate)}</p>)}<hr/><b>Grand Total: {money(p.totals.total)}</b></div></div>{p.irn&&<div className="panel"><h2>E-Invoice</h2><p><b>IRN</b><br/><small>{p.irn.irn}</small></p><p>Ack No.: {p.irn.ack_no||'—'}</p></div>}</aside></div></>}

function Returns(p:any){return <><section className="top"><div><h1>Returns & Filing Readiness</h1><p>Draft, review, validate and lock periods before filing.</p></div><input value={p.period} onChange={e=>p.setPeriod(e.target.value)}/></section><div className="returnGrid"><div className="infoPanel"><h2>GSTR-1</h2><p>B2B: {p.gstr1?.b2b?.length??'—'} · B2C: {p.gstr1?.b2c?.length??'—'} · CDNR: {p.gstr1?.cdnr?.length??'—'}</p><p>HSN rows: {p.gstr1?.hsn_summary?.length??'—'}</p><button className="primaryBtn" onClick={()=>p.loadReturn('GSTR1')}>Generate Draft</button>{p.gstr1&&<button onClick={()=>p.lockReturn('GSTR1')}><Lock size={14}/> Lock Period</button>}</div><div className="infoPanel"><h2>GSTR-3B</h2><p>Output: {p.gstr3b?money(Number(p.gstr3b.outward_supplies.cgst)+Number(p.gstr3b.outward_supplies.sgst)+Number(p.gstr3b.outward_supplies.igst)):'—'}</p><p>ITC: {p.gstr3b?money(Number(p.gstr3b.itc_available.cgst)+Number(p.gstr3b.itc_available.sgst)+Number(p.gstr3b.itc_available.igst)):'—'}</p><button className="primaryBtn" onClick={()=>p.loadReturn('GSTR3B')}>Generate Draft</button>{p.gstr3b&&<button onClick={()=>p.lockReturn('GSTR3B')}><Lock size={14}/> Lock Period</button>}</div></div><div className="panel" style={{margin:'14px 22px'}}><h2>Exports</h2><button className="exportLink" onClick={()=>p.download('/api/export/gstr1.csv?period='+p.period+'&company_id='+encodeURIComponent(p.company?.id||''),'gstr1-'+p.period+'.csv')}>Download GSTR-1 CSV</button><span> · </span><button className="exportLink" onClick={()=>p.download('/api/export/invoices.xlsx?period='+p.period+'&company_id='+encodeURIComponent(p.company?.id||''),'invoices-'+p.period+'.xlsx')}>Download Invoice Excel</button></div></>}

function Reconciliation(p:any){return <><section className="top"><div><h1>Reconciliation</h1><p>Surface missing IRNs, unmatched purchases and compliance exceptions.</p></div><input value={p.period} onChange={e=>p.setPeriod(e.target.value)}/></section><div className="dashGrid"><div className="metric"><span>Matched</span><b>{p.recon?.summary?.ok??'—'}</b></div><div className="metric"><span>Exceptions</span><b>{p.recon?.summary?.exceptions??'—'}</b></div></div><div className="panel" style={{margin:'14px 22px'}}><button className="primaryBtn" onClick={p.load}><Search size={14}/> Run reconciliation</button>{p.recon?.rows?.map((r:any)=><div className="reconRow" key={r.invoice_id||r.purchase_id}><b>{r.invoice_no}</b><span>{r.bucket}</span><span>{r.irn_status||r.gstr2b_status}</span></div>)}</div></>}

function Masters(p:any){const rows=p.active==='Products / Services'?p.products:p.active==='Vendors'?p.vendors:p.customers;return <><section className="top"><div><h1>{p.active}</h1><p>Production company-scoped master data.</p></div><button className="primaryBtn" onClick={p.reload}>Refresh</button></section><div className="panel" style={{margin:'0 22px'}}><table className="masterTable"><thead><tr><th>Name</th><th>GSTIN</th><th>State</th><th>HSN / Rate</th></tr></thead><tbody>{rows?.map((r:any)=><tr key={r.id}><td>{r.description||r.name}</td><td>{r.gstin||'—'}</td><td>{r.state_code||'—'}</td><td>{r.hsn_sac?String(r.hsn_sac)+' · '+r.gst_rate+'%':r.rate?money(r.rate):'—'}</td></tr>)}</tbody></table></div></>}

function CompanyView({company,gstins}:any){return <><section className="top"><div><h1>Company / GSTINs</h1><p>Tenant context used by every production transaction.</p></div></section><div className="bottom"><div className="infoPanel"><h2>{company?.trade_name||company?.legal_name||'Company'}</h2><p>PAN: {company?.pan||'—'}</p><p>AATO: {money(company?.aato)}</p><p>{company?.address?.city||''}, {company?.address?.state||''} {company?.address?.pincode||''}</p></div>{gstins?.map((g:any)=><div className="infoPanel" key={g.id}><h2>GSTIN</h2><p><b>{g.gstin}</b></p><p>State: {g.state_code}</p><p>Scheme: {g.scheme}</p><p>E-invoice: {g.e_invoice_enabled?'Enabled':'Disabled'}</p></div>)}</div></>}

function UsersView({token,company,can}:any){const [rows,setRows]=useState<any[]>([]);const [error,setError]=useState('');useEffect(()=>{if(can('admin')&&company)api('/api/users?company_id='+encodeURIComponent(company.id),token).then(setRows).catch(e=>setError(e.message));},[token,company?.id]);return <><section className="top"><div><h1>Users & Roles</h1><p>Company-scoped identities and maker-checker roles.</p></div></section><div className="panel" style={{margin:'0 22px'}}>{error&&<div className="error">{error}</div>}<table className="masterTable"><thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Active</th></tr></thead><tbody>{rows.map(r=><tr key={r.id}><td>{r.name}</td><td>{r.email}</td><td>{r.role}</td><td>{r.is_active===false?'No':'Yes'}</td></tr>)}</tbody></table></div></>}

function Reports({period,company,download}:any){return <><section className="top"><div><h1>Reports</h1><p>Authenticated production exports for the selected company and period.</p></div></section><div className="returnGrid"><div className="infoPanel"><h2>GSTR-1 CSV</h2><p>{period}</p><button className="primaryBtn" onClick={()=>download('/api/export/gstr1.csv?period='+period+'&company_id='+encodeURIComponent(company?.id||''),'gstr1-'+period+'.csv')}><Download size={14}/> Export</button></div><div className="infoPanel"><h2>Invoice Excel</h2><p>{period}</p><button className="primaryBtn" onClick={()=>download('/api/export/invoices.xlsx?period='+period+'&company_id='+encodeURIComponent(company?.id||''),'invoices-'+period+'.xlsx')}><Download size={14}/> Export</button></div></div></>}

function PresetView(){return <><section className="top"><div><h1>GST Rate Presets</h1><p>Configured presets available to the invoice workspace.</p></div></section><div className="dashGrid">{Object.values(presets).map((p:any)=><div className="metric" key={p.name}><span>{p.scheme}</span><b>{p.rate}%</b><small>{p.name}</small></div>)}</div></>}

function EInvoiceView({savedId,status,irn}:any){return <><section className="top"><div><h1>E-Invoice</h1><p>IRN generation is available only after maker-checker approval.</p></div></section><div className="infoPanel" style={{margin:'0 22px'}}><p>Invoice: {savedId||'—'}</p><p>Status: <b>{status||'—'}</b></p>{irn?<><p>IRN: {irn.irn}</p><p>Ack No.: {irn.ack_no||'—'}</p></>:<p>No e-invoice generated in this session.</p>}</div></>}

function SettingsView({user,company}:any){return <><section className="top"><div><h1>Settings</h1><p>Current authenticated context.</p></div></section><div className="bottom"><div className="infoPanel"><h2>User</h2><p>{user?.name}</p><p>{user?.email}</p><p>Role: {user?.role}</p></div><div className="infoPanel"><h2>Company</h2><p>{company?.trade_name||company?.legal_name}</p><p>Company ID: {company?.id}</p></div></div></>}

