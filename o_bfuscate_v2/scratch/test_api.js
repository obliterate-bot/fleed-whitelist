const http = require('http');

const req = http.request('http://localhost:3000/api/obfuscate', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' }
}, (res) => {
  let body = '';
  res.on('data', d => body += d);
  res.on('end', () => {
    console.log('API Status:', res.statusCode);
    const json = JSON.parse(body);
    console.log('Success:', json.success);
    console.log('Stats:', json.stats);
    console.log('Sample Code:', json.code.substring(0, 180));
  });
});

req.write(JSON.stringify({
  code: 'local function test() print("hello world") end; test()',
  preset: 'ultra-secure'
}));
req.end();
