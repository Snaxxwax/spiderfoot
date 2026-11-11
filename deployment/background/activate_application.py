"""Activate tested background API/UI images without altering scanner isolation."""
from pathlib import Path
import subprocess,json,re,os
root=Path('/opt/harvest/spiderfoot-ng'); receipt=root/'deployment/background/deployment.json'
r=json.loads(receipt.read_text())
assert r['state']=='prepared', 'Inspect prior activation before repeating'
def image(tag):return subprocess.check_output(['docker','image','inspect',tag,'--format','{{.Id}}'],text=True).strip()
r['previous_frontend_image']=json.loads(subprocess.check_output(['docker','inspect','sf-frontend-ui']))[0]['Image']
values={'SF_API_IMAGE':image('spiderfoot-api:background-20261109'),'SF_BACKGROUND_IMAGE':image('spiderfoot-api:background-20261109'),'SF_FRONTEND_IMAGE':image('spiderfoot-frontend:background-20261109')}
p=root/'.env';s=p.read_text()
for k,v in values.items():s=re.sub(r'^'+k+r'=.*$',lambda _:k+'='+v,s,flags=re.M)
p.write_text(s);os.chmod(p,0o600)
p=root/'compose.core.yml';s=p.read_text();a,b=s.split('  api:\n',1);b,c=b.split('  celery-worker:\n',1)
for key in ('SF_MINIO_ENABLED','SF_QDRANT_ENABLED','SF_VECTOR_ENABLED'):b=b.replace(key+': "false"',key+': "true"')
b=b.replace('    environment:\n','''    environment:
      SF_BACKGROUND_ENABLED: "true"
      SF_BACKGROUND_SINCE_MS: ${SF_BACKGROUND_SINCE_MS}
      SF_QDRANT_API_KEY: ${SF_QDRANT_API_KEY}
      SF_LLM_API_KEY: ${OPENROUTER_API_KEY}
      SF_EMBEDDING_API_KEY: ${OPENROUTER_API_KEY}
      SF_VECTOR_ENDPOINT: http://vector:8686
      VECTOR_API_URL: http://vector:8687
''',1)
p.write_text(a+'  api:\n'+b+'  celery-worker:\n'+c)
subprocess.run(['docker','compose','-f','compose.core.yml','config','--quiet'],cwd=root,check=True)
r['images'].update(values);r['state']='application_prepared';r['verification_scan']='BF4808E5';r['openrouter_request_id']='gen-1794261717-Q74uOTIkzMdsIPAsTSCt';receipt.write_text(json.dumps(r,indent=2))
print('API, UI, and background image identities recorded; Compose validated')
