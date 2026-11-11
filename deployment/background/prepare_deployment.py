"""Prepare deterministic background services while preserving deployment settings."""
import json, os, re, secrets, shutil, subprocess, time
from pathlib import Path
root=Path('/opt/harvest/spiderfoot-ng')
operation=root/'deployment/background/deployment.json'
if operation.exists():
    raise SystemExit('Operation already prepared; inspect receipt before retrying')
compose=root/'compose.core.yml'; env=root/'.env'
for path in (compose,env):
    backup=path.with_name(path.name+'.before-background-20261109')
    if backup.exists():raise SystemExit('Backup exists; inspect before retry')
    shutil.copy2(path,backup)
    if path==env:os.chmod(backup,0o600)
def image_id(name):
    return json.loads(subprocess.check_output(['docker','image','inspect',name]))[0]['Id']
api=json.loads(subprocess.check_output(['docker','inspect','sf-api']))[0]
runtime=dict(v.split('=',1) for v in api['Config']['Env'])
values={
 'SF_MINIO_IMAGE':image_id('spiderfoot-minio:7aac2a2'),
 'SF_QDRANT_IMAGE':image_id('qdrant/qdrant:v1.12.4'),
 'SF_VECTOR_IMAGE':image_id('timberio/vector:0.60.0-alpine'),
 'SF_BACKGROUND_IMAGE':image_id('spiderfoot-api:background-20261109'),
 'SF_POSTGRES_DSN':runtime['SF_POSTGRES_DSN'],
 'SF_BACKGROUND_SINCE_MS':str(int(time.time()*1000)),
 'MINIO_ROOT_USER':'sf-storage', 'MINIO_ROOT_PASSWORD':secrets.token_urlsafe(40),
 'SF_QDRANT_API_KEY':secrets.token_urlsafe(40),
 'SF_MINIO_ENDPOINT':'minio:9000','SF_MINIO_SECURE':'false',
 'SF_QDRANT_BACKEND':'http','SF_QDRANT_HOST':'qdrant','SF_QDRANT_PORT':'6333',
 'SF_QDRANT_GRPC_PORT':'6334','SF_QDRANT_PREFIX':'sf_',
 'SF_EMBEDDING_PROVIDER':'openai','SF_EMBEDDING_MODEL':'openai/text-embedding-3-small',
 'SF_EMBEDDING_DIMENSIONS':'1536','SF_EMBEDDING_API_BASE':'https://openrouter.ai/api/v1',
 'SF_LLM_PROVIDER':'openai','SF_LLM_MODEL':'openai/gpt-6-astra','SF_LLM_API_BASE':'https://openrouter.ai/api/v1',
 'SF_VECTOR_URL':'http://vector:8686',
}
s=env.read_text()
for k,v in values.items():
    pattern=r'^'+re.escape(k)+r'=(.*)$'
    existing=re.search(pattern,s,re.M)
    if existing and k in ('MINIO_ROOT_USER','MINIO_ROOT_PASSWORD','SF_QDRANT_API_KEY') and existing.group(1).strip():continue
    if existing:s=re.sub(pattern,lambda _:k+'='+v,s,flags=re.M)
    else:s+='\n'+k+'='+v
s+='\n';env.write_text(s);os.chmod(env,0o600)
c=compose.read_text();c=c.replace('services:\n','services:\n'+(root/'deployment/background/services.yml').read_text()+'\n',1)
c+='\nvolumes:\n  sf-background-minio:\n  sf-background-qdrant:\n  sf-background-snapshots:\n  sf-background-vector:\n'
compose.write_text(c)
record={'operation_id':'background-20261109','state':'prepared','previous_api_image':api['Image'],
 'images':{k:v for k,v in values.items() if k.endswith('_IMAGE')},'since_ms':values['SF_BACKGROUND_SINCE_MS']}
operation.write_text(json.dumps(record,indent=2))
subprocess.run(['docker','compose','-f','compose.core.yml','config','--quiet'],cwd=root,check=True)
print('Compose validated; credentials retained privately in the deployment environment.')
