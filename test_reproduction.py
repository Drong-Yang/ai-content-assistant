"""Uses the project PostgreSQL database and deterministic mock model/image services."""
import asyncio
import base64
import os
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import httpx

os.environ['MOCK_MODE']='true'
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from fastapi.testclient import TestClient
from app.main import app
from app.dependencies.auth import get_current_user
from app.services.image_service import ImageService


class WorkflowTests(unittest.TestCase):
    def test_full_flow_rewrite_restart_isolation_partial_failure_retry(self):
        suffix=uuid.uuid4().hex[:10]
        with TestClient(app) as client:
            def register(name):
                r=client.post('/api/v1/auth/register',json={'username':name,'password':'TestPassword123!'})
                self.assertEqual(r.status_code,200,r.text)
                r=client.post('/api/v1/auth/login',json={'username':name,'password':'TestPassword123!'})
                self.assertEqual(r.status_code,200,r.text)
                return {'Authorization':'Bearer '+r.json()['access_token']}
            owner=register('test_owner_'+suffix);other=register('test_other_'+suffix)
            r=client.post('/api/v1/workflow/start',json={'topic_direction':'Python'},headers=owner)
            self.assertEqual(r.status_code,200,r.text)
            data=r.json();thread=data['thread_id'];topic=data['generated_topics'][0]
            self.assertEqual(data['status'],'topics_generated')
            for method,url,body in [
                ('get',f'/state/{thread}',None),('get',f'/history/{thread}',None),
                ('post',f'/resume/{thread}',{'action':'approve'}),
                ('post',f'/stream/resume/{thread}',{'action':'reject'}),
                ('post',f'/retry/{thread}',{}),('delete',f'/threads/{thread}',None)]:
                r=client.request(method,'/api/v1/workflow'+url,json=body,headers=other)
                self.assertEqual(r.status_code,403,r.text)
            # Even a shared textual prefix must not pass ownership checks.
            app.dependency_overrides[get_current_user]=lambda:SimpleNamespace(id=thread.split('_')[0][:-1])
            self.assertEqual(client.get('/api/v1/workflow/history/'+thread).status_code,403)
            app.dependency_overrides.clear()
            r=client.post('/api/v1/workflow/resume/'+thread,headers=owner,json={'action':'select_topic','data':{'selected_topic':'invalid'}})
            self.assertEqual(r.status_code,400)
            r=client.post('/api/v1/workflow/stream/resume/'+thread,headers=owner,json={'action':'select_topic','data':{'selected_topic':topic}})
            self.assertEqual(r.status_code,200,r.text);self.assertIn('"type": "done"',r.text)
            r=client.post('/api/v1/workflow/resume/'+thread,headers=owner,json={'action':'reject','data':{'feedback':'增加API实例'}})
            self.assertEqual(r.status_code,200,r.text)
            state=client.get('/api/v1/workflow/state/'+thread,headers=owner).json()
            self.assertEqual(state['values']['revision_count'],1)
            self.assertIn('增加API实例',state['values']['article_content'])
            with patch('app.graph.nodes.visualizer.get_image_service') as image:
                image.return_value.generate_images=unittest.mock.AsyncMock(return_value=['/static/partial-test.svg'])
                r=client.post('/api/v1/workflow/resume/'+thread,headers=owner,json={'action':'approve'})
            self.assertEqual(r.status_code,200,r.text)
            self.assertEqual(r.json()['status'],'images_failed')
            self.assertFalse(r.json()['is_completed'])
            self.assertTrue(r.json()['result']['error'])
            self.assertEqual(len(client.get('/api/v1/workflow/threads',headers=other).json()['threads']),0)
        # Fresh application lifespan + new graph + reopened PostgreSQL connection.
        with TestClient(app) as client:
            state=client.get('/api/v1/workflow/state/'+thread,headers=owner)
            self.assertEqual(state.status_code,200,state.text)
            self.assertEqual(state.json()['status'],'images_failed')
            r=client.post('/api/v1/workflow/retry/'+thread,headers=owner)
            self.assertEqual(r.status_code,200,r.text)
            self.assertTrue(r.json()['is_completed'],r.text)
            self.assertEqual(len(r.json()['values']['image_urls']),3)
            self.assertGreater(client.get('/api/v1/workflow/history/'+thread,headers=owner).json()['total'],0)
            listed=client.get('/api/v1/workflow/threads',headers=owner).json()['threads']
            self.assertTrue(any(t['thread_id']==thread for t in listed))
            self.assertEqual(client.delete('/api/v1/workflow/threads/'+thread,headers=owner).status_code,200)
            self.assertEqual(client.get('/api/v1/workflow/state/'+thread,headers=owner).status_code,404)

    def test_failed_writer_retries_from_checkpoint(self):
        with TestClient(app) as client:
            credentials={'username':'retry_'+uuid.uuid4().hex[:10],'password':'TestPassword123!'}
            client.post('/api/v1/auth/register',json=credentials)
            r=client.post('/api/v1/auth/login',json=credentials)
            headers={'Authorization':'Bearer '+r.json()['access_token']}
            data=client.post('/api/v1/workflow/start',headers=headers,json={'topic_direction':'API'}).json()
            thread=data['thread_id']
            with patch('app.graph.nodes.writer.get_llm_service',side_effect=RuntimeError('injected timeout')):
                r=client.post('/api/v1/workflow/resume/'+thread,headers=headers,json={'action':'select_topic','data':{'selected_topic':data['generated_topics'][0]}})
            self.assertEqual(r.status_code,500)
            r=client.post('/api/v1/workflow/retry/'+thread,headers=headers)
            self.assertEqual(r.status_code,200,r.text)
            self.assertEqual(r.json()['interrupt_info']['action_required'],'review')
            client.delete('/api/v1/workflow/threads/'+thread,headers=headers)


class ImageTests(unittest.IsolatedAsyncioTestCase):
    async def test_ark_payload_and_auth_failure_no_unrelated_retry(self):
        captured=[]
        def respond(request):
            import json
            captured.append(json.loads(request.content))
            return httpx.Response(401,json={'error':{'code':'InvalidApiKey'}})
        original=httpx.AsyncClient
        with patch.dict(os.environ,{'MOCK_MODE':'false','IMAGE_MODEL':'test-image','IMAGE_API_KEY':'test-key'}):
            service=ImageService()
        with patch('app.services.image_service.httpx.AsyncClient',side_effect=lambda **kw:original(transport=httpx.MockTransport(respond),**kw)):
            with self.assertRaises(RuntimeError):
                await service.generate_single_image('FastAPI流程')
        self.assertEqual(len(captured),1)
        self.assertEqual(captured[0]['response_format'],'b64_json')
        self.assertIn('FastAPI流程',captured[0]['prompt'])


if __name__=='__main__': unittest.main()
