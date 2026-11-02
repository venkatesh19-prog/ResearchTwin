const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../../frontend/frontend-config.js'), 'utf8');

for (const hostname of ['localhost', '127.0.0.1', '[::1]']) {
    test(`local development on ${hostname} uses the local API`, () => {
        const window = { location: { hostname } };
        vm.runInNewContext(source, { window });
        assert.equal(window.RESEARCHTWIN_API_BASE, 'http://127.0.0.1:8000');
    });
}

test('explicit API configuration is preserved', () => {
    const window = { location: { hostname: 'localhost' }, RESEARCHTWIN_API_BASE: 'http://127.0.0.1:8799' };
    vm.runInNewContext(source, { window });
    assert.equal(window.RESEARCHTWIN_API_BASE, 'http://127.0.0.1:8799');
});

test('the reviewed Netlify production host uses the Render API', () => {
    const window = { location: { hostname: 'starlit-empanada-a323e3.netlify.app' } };
    vm.runInNewContext(source, { window });
    assert.equal(window.RESEARCHTWIN_API_BASE, 'https://researchtwin-api.onrender.com');
});

test('an unknown deployment host has no API endpoint', () => {
    const window = { location: { hostname: 'preview.example.test' } };
    vm.runInNewContext(source, { window });
    assert.equal(window.RESEARCHTWIN_API_BASE, undefined);
});

test('an unknown deployment cannot inherit an API endpoint from another host', () => {
    const window = { location: { hostname: 'starlit-empanada-a323e3.netlify.app.evil.test' } };
    vm.runInNewContext(source, { window });
    assert.equal(window.RESEARCHTWIN_API_BASE, undefined);
});
