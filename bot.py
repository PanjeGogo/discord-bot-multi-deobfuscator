import os,io,re,json,asyncio,aiohttp,discord,uuid,time,logging
from pathlib import Path
from datetime import datetime,timezone
from discord.ext import commands
from dotenv import load_dotenv
from engines import analyze_and_rewrite

load_dotenv()
BASE=Path(__file__).resolve().parent; TEMP=BASE/'temp'; JOBS=TEMP/'jobs'; LOGS=TEMP/'logs'; PROGRESS=TEMP/'progress.json'
for d in (TEMP,JOBS,LOGS): d.mkdir(parents=True,exist_ok=True)
if not PROGRESS.exists(): PROGRESS.write_text(json.dumps({'version':1,'jobs':{}},indent=2),encoding='utf8')
TOKEN=os.getenv('DISCORD_TOKEN',''); KEY=os.getenv('GEMINI_API_KEY',''); MODEL=os.getenv('GEMINI_MODEL','gemini-2.5-flash'); PREFIX=os.getenv('PREFIX','!'); MAX_PASSES=int(os.getenv('MAX_PASSES','100')); MAX_FILE_BYTES=int(os.getenv('MAX_FILE_BYTES','2000000')); MAX_CONCURRENT=int(os.getenv('MAX_CONCURRENT_JOBS','1'))
logging.basicConfig(level=logging.INFO,format='%(asctime)s | %(levelname)s | %(message)s',handlers=[logging.StreamHandler(),logging.FileHandler(LOGS/'bot.log',encoding='utf8')]); log=logging.getLogger('deobfus')
intents=discord.Intents.default(); intents.message_content=True; bot=commands.Bot(command_prefix=PREFIX,intents=intents,help_command=None)
running={}; lock=asyncio.Lock()

def now(): return datetime.now(timezone.utc).isoformat()
def atomic_json(path,data):
    tmp=path.with_suffix(path.suffix+'.tmp'); tmp.write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding='utf8'); os.replace(tmp,path)
async def save_state(state):
    state['updated_at']=now(); p=JOBS/state['job_id']; atomic_json(p/'state.json',state)
    async with lock:
        try: allp=json.loads(PROGRESS.read_text(encoding='utf8'))
        except: allp={'version':1,'jobs':{}}
        allp.setdefault('jobs',{})[state['job_id']]=state; atomic_json(PROGRESS,allp)

def detect(s):
    scores={'luraph_v14':0,'moonsec_v3':0,'wearedevs_v1':0}; ev={k:[] for k in scores}
    if len(re.findall(r'\b(?:local|for)\s+\w+\s*=\s*\{',s))>=5: scores['luraph_v14']+=2; ev['luraph_v14'].append('many local tables')
    if len(re.findall(r'\w+\s*\[\s*\w+\s*\]\s*\[\s*',s))>=8: scores['luraph_v14']+=2; ev['luraph_v14'].append('nested table access')
    if 'bit32.' in s: scores['luraph_v14']+=1; ev['luraph_v14'].append('bit32')
    if any(x in s for x in ('MS_ENCRYPT','ENCRYPT:','MOONSEC_EXIT','MOONSEC_GET_SCRIPT_ID')): scores['moonsec_v3']+=3; ev['moonsec_v3'].append('MoonSec markers')
    if 'loadstring' in s: scores['wearedevs_v1']+=1; ev['wearedevs_v1'].append('loadstring')
    if re.search(r'\b(?:getgenv|checkcaller|identifyexecutor)\b',s): scores['wearedevs_v1']+=1; ev['wearedevs_v1'].append('environment checks')
    f=max(scores,key=scores.get); return (f if scores[f]>=3 else 'generic'),scores,ev

def profile(family):
    p=BASE/'profiles'/f'{family}.json'
    try: return json.loads(p.read_text(encoding='utf8'))
    except: return {}

def clean(x):
    x=x.strip(); m=re.search(r'```(?:lua)?\s*(.*?)```',x,re.I|re.S); return m.group(1).strip() if m else x

async def ask(session,prompt):
    if not KEY: raise RuntimeError('GEMINI_API_KEY belum diisi.')
    url=f'https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={KEY}'
    body={'system_instruction':{'parts':[{'text':'Analyze Lua as text only. Never execute it. Recover readable, semantically equivalent Lua when justified. Preserve Roblox/Lua APIs. Do not invent behavior. Return only Lua source.'}]},'contents':[{'role':'user','parts':[{'text':prompt}]}],'generationConfig':{'temperature':0.1,'maxOutputTokens':65536}}
    for i in range(6):
        try:
            async with session.post(url,json=body,timeout=aiohttp.ClientTimeout(total=240)) as r:
                txt=await r.text()
                if r.status==429 or r.status>=500:
                    await asyncio.sleep(min(60,2**i+1)); continue
                if r.status>=400: raise RuntimeError(f'Gemini HTTP {r.status}: {txt[:500]}')
                d=json.loads(txt); return d['candidates'][0]['content']['parts'][0]['text']
        except (aiohttp.ClientError,asyncio.TimeoutError):
            if i==5: raise
            await asyncio.sleep(min(30,2**i+1))
    raise RuntimeError('Gemini rate limit/server error persisted.')

def embed(s,title=None):
    st=s.get('status','processing'); color=discord.Color.blurple() if st=='processing' else discord.Color.green() if st=='completed' else discord.Color.red()
    title=title or ({'processing':'🔄 Deobfuscating Lua','completed':'✅ Deobfuscation selesai','cancelled':'🛑 Deobfuscation dibatalkan','error':'❌ Deobfuscation gagal'}.get(st,'Lua Deobfuscator'))
    e=discord.Embed(title=title,description=s.get('message',''),color=color)
    e.add_field(name='File',value=f"`{s.get('filename','-')}`",inline=False); e.add_field(name='Profile',value=f"`{s.get('family','generic')}`",inline=True); e.add_field(name='Pass',value=f"`{s.get('pass',0)}/{s.get('max_passes',MAX_PASSES)}`",inline=True); e.add_field(name='Gemini requests',value=f"`{s.get('requests',0)}`",inline=True)
    if s.get('error'): e.add_field(name='Error',value=f"```{s['error'][:900]}```",inline=False)
    e.set_footer(text=f"Job: {s.get('job_id','-')}"); return e

class Cancel(discord.ui.Button):
    def __init__(self,jid): super().__init__(label='Batalkan',emoji='🛑',style=discord.ButtonStyle.danger,custom_id=f'cancel:{jid}'); self.jid=jid
    async def callback(self,interaction):
        p=JOBS/self.jid/'state.json'
        if not p.exists(): return await interaction.response.send_message('❌ Job tidak ditemukan.',ephemeral=True)
        s=json.loads(p.read_text(encoding='utf8')); owner=interaction.user.id==int(s['user_id']); admin=bool(interaction.guild and interaction.user.guild_permissions.administrator)
        if not(owner or admin): return await interaction.response.send_message('❌ Hanya pengirim file atau admin server yang dapat membatalkan.',ephemeral=True)
        s['cancel_requested']=True; s['cancelled_by']=interaction.user.id; s['status']='cancelling'; await save_state(s)
        t=running.get(self.jid)
        if t and not t.done(): t.cancel()
        await interaction.response.send_message('🛑 Proses dibatalkan.',ephemeral=True)

def view(jid,disabled=False):
    v=discord.ui.View(timeout=None); b=Cancel(jid); b.disabled=disabled; v.add_item(b); return v

async def process(msg,jid):
    d=JOBS/jid; state=json.loads((d/'state.json').read_text(encoding='utf8')); src=(d/'current.lua').read_text(encoding='utf8')
    try:
        async with aiohttp.ClientSession() as session:
            for n in range(state['pass']+1,state['max_passes']+1):
                if state.get('cancel_requested'): raise asyncio.CancelledError
                state.update(status='processing',pass=n,message=f'🧠 Gemini reconstruction — pass {n}/{state["max_passes"]}'); await save_state(state); await msg.edit(embed=embed(state),view=view(jid))
                # Local non-executing pass: cheap Luraph rewrites before Gemini.
                local=analyze_and_rewrite(src,state['family'])
                if local.changed:
                    (d/'previous.lua').write_text(src,encoding='utf8')
                    (d/f'local_{n:03d}.lua').write_text(local.source,encoding='utf8')
                    (d/'current.lua').write_text(local.source,encoding='utf8')
                    src=local.source; state['pass']=n; state['local_steps']=state.get('local_steps',0)+1
                    state['message']='⚙️ Local Luraph engine: '+('; '.join(local.notes)[:700])
                    await save_state(state); await msg.edit(embed=embed(state),view=view(jid))
                    continue
                prof=profile(state['family']); prompt=f"Detected profile: {state['family']}\nProfile: {json.dumps(prof)[:14000]}\nEvidence: {json.dumps(state.get('evidence',[]))}\nPass {n}. Deobfuscate the CURRENT Lua statically. Preserve behavior. Remove only justified obfuscation/junk. Return ONLY complete Lua source.\n\nCURRENT SOURCE:\n{src}"
                state['requests']+=1; await save_state(state); new=clean(await ask(session,prompt))
                if len(new)<20: raise RuntimeError('Gemini returned source that is too short.')
                (d/'previous.lua').write_text(src,encoding='utf8'); (d/f'pass_{n:03d}.lua').write_text(new,encoding='utf8'); (d/'current.lua').write_text(new,encoding='utf8')
                old=src; src=new; state['pass']=n; await save_state(state)
                if new.strip()==old.strip(): break
            if state.get('cancel_requested'): raise asyncio.CancelledError
            (d/'result.lua').write_text(src,encoding='utf8'); state.update(status='completed',message='Source hasil deobfuscation siap.',result_path=str(d/'result.lua')); await save_state(state); await msg.edit(embed=embed(state),view=view(jid,True))
            await msg.channel.send(file=discord.File(io.BytesIO(src.encode()),filename='deobfuscated_'+state['filename']))
    except asyncio.CancelledError:
        state['status']='cancelled'; state['message']='Proses dihentikan. Checkpoint tetap tersimpan di temp/jobs.'; await save_state(state); await msg.edit(embed=embed(state),view=view(jid,True))
    except Exception as e:
        log.exception('job %s failed',jid); state['status']='error'; state['error']=str(e); state['message']='Terjadi error saat deobfuscation.'; await save_state(state); await msg.edit(embed=embed(state),view=view(jid,True))
    finally: running.pop(jid,None)

@bot.command(name='deobfus')
@commands.cooldown(1,15,commands.BucketType.user)
async def deobfus(ctx):
    if not ctx.message.attachments: return await ctx.reply('❌ Lampirkan file `.lua`, lalu gunakan `!deobfus`.')
    a=ctx.message.attachments[0]
    if not a.filename.lower().endswith('.lua'): return await ctx.reply('❌ File harus `.lua`.')
    if sum(not t.done() for t in running.values())>=MAX_CONCURRENT: return await ctx.reply('⏳ Bot sedang sibuk memproses job lain.')
    raw=await a.read()
    if len(raw)>MAX_FILE_BYTES: return await ctx.reply('❌ File terlalu besar.')
    src=raw.decode('utf8','replace'); family,scores,ev=detect(src); jid=uuid.uuid4().hex[:12]; d=JOBS/jid; d.mkdir(parents=True)
    (d/'input.lua').write_text(src,encoding='utf8'); (d/'current.lua').write_text(src,encoding='utf8')
    s={'version':1,'job_id':jid,'message_id':ctx.message.id,'channel_id':ctx.channel.id,'guild_id':ctx.guild.id if ctx.guild else None,'user_id':ctx.author.id,'filename':a.filename,'family':family,'scores':scores,'evidence':ev.get(family,[]),'status':'processing','message':'📥 File diterima; fingerprint lokal selesai.','pass':0,'max_passes':MAX_PASSES,'requests':0,'local_steps':0,'started_at':now(),'updated_at':now(),'cancel_requested':False,'cancelled_by':None,'result_path':None,'error':None}
    await save_state(s); msg=await ctx.reply(embed=embed(s),view=view(jid)); s['status_message_id']=msg.id; await save_state(s); running[jid]=asyncio.create_task(process(msg,jid))

@deobfus.error
async def derr(ctx,e):
    if isinstance(e,commands.CommandOnCooldown): await ctx.reply(f'⏳ Tunggu {e.retry_after:.1f} detik.')
    else: await ctx.reply(f'❌ {e}')

@bot.event
async def on_ready(): log.info('Logged in as %s | Gemini=%s',bot.user,MODEL)

bot.run(TOKEN)
