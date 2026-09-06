import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  stages: [
    { duration: '30s', target: 20 },
    { duration: '4m', target: 20 },
    { duration: '30s', target: 0 },
  ],
};

export default function () {
  const url = __ENV.TARGET_URL || 'http://127.0.0.1:8000/';
  const res = http.get(url, { headers: { 'Host': 'myapp.local' } });
  check(res, {
    'is status 200': (r) => r.status === 200,
  });
  sleep(0.1);
}
