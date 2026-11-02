const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const frontend = path.join(__dirname, '../../frontend');
const headers = fs.readFileSync(path.join(frontend, '_headers'), 'utf8');
const html = fs.readFileSync(path.join(frontend, 'researchtwin.html'), 'utf8');
const indexHtml = fs.readFileSync(path.join(frontend, 'index.html'), 'utf8');
const config = fs.readFileSync(path.join(frontend, 'frontend-config.js'), 'utf8');

function directive(name) {
    const match = headers.match(new RegExp(`^\\s*${name}:\\s*(.+)$`, 'm'));
    return match ? match[1].trim() : null;
}

function cspSources(name) {
    const csp = directive('Content-Security-Policy') || '';
    const match = csp.match(new RegExp(`(?:^|;)\\s*${name}\\s+([^;]+)`));
    return match ? match[1].trim().split(/\s+/) : [];
}

test('security headers are sent for every static asset', () => {
    assert.match(headers, /^\/\*$/m);
    assert.equal(directive('X-Content-Type-Options'), 'nosniff');
    assert.equal(directive('X-Frame-Options'), 'DENY');
    assert.equal(directive('Referrer-Policy'), 'no-referrer');
    assert.match(directive('Strict-Transport-Security'), /max-age=31536000/);
});

test('content security policy allows the real inline and CDN assets', () => {
    const csp = directive('Content-Security-Policy');

    assert.ok(csp, 'Content-Security-Policy must be present');
    for (const page of [indexHtml, html]) {
        assert.match(page, /<style>/);
        assert.match(page, /<script>/);
        assert.match(page, /onclick=/);
    }

    assert.match(csp, /script-src 'self' 'unsafe-inline'/);
    assert.match(csp, /style-src 'self' 'unsafe-inline' https:\/\/cdnjs\.cloudflare\.com/);
    assert.match(csp, /font-src 'self' data: https:\/\/cdnjs\.cloudflare\.com/);
    assert.match(html, /https:\/\/cdnjs\.cloudflare\.com\/ajax\/libs\/font-awesome/);
});

test('content security policy allows only the known API origins', () => {
    const csp = directive('Content-Security-Policy');
    const connect = csp.match(/connect-src ([^;]+)/)[1];

    assert.match(config, /https:\/\/researchtwin-api\.onrender\.com/);
    assert.match(connect, /https:\/\/researchtwin-api\.onrender\.com/);
    assert.match(connect, /http:\/\/127\.0\.0\.1:8000/);
    assert.match(connect, /http:\/\/localhost:8000/);
});

test('content security policy fails closed for framing and objects', () => {
    const csp = directive('Content-Security-Policy');

    assert.match(csp, /default-src 'self'/);
    assert.match(csp, /object-src 'none'/);
    assert.match(csp, /base-uri 'self'/);
    assert.match(csp, /frame-ancestors 'none'/);
    assert.doesNotMatch(csp, /'unsafe-eval'/);
    assert.doesNotMatch(csp, /default-src \*/);
});

const ASSET_DIRECTIVE = {
    link: 'style-src',
    img: 'img-src',
    script: 'script-src',
    source: 'media-src',
};

test('every external asset on both entry pages is permitted by the CSP', () => {
    for (const [page, source] of [
        ['index.html', indexHtml],
        ['researchtwin.html', html],
    ]) {
        const pattern = /<(link|img|script|source)\b[^>]*?\b(?:src|href)="(https?:\/\/[^"]+)"/g;
        let match;
        let checked = 0;

        while ((match = pattern.exec(source)) !== null) {
            const [, tag, url] = match;
            const origin = new URL(url).origin;
            const sources = cspSources(ASSET_DIRECTIVE[tag]);

            assert.ok(
                sources.includes(origin),
                `${page} loads ${url} but CSP ${ASSET_DIRECTIVE[tag]} does not allow ${origin}`
            );
            checked += 1;
        }

        assert.ok(checked > 0, `${page} must reference at least one external asset to check`);
    }
});

test('image policy allows the ranking banner origin without a wildcard', () => {
    const img = cspSources('img-src');

    assert.ok(img.includes("'self'"));
    assert.ok(img.includes('data:'));
    assert.ok(img.includes('https://www.lpu.in'));
    assert.ok(!img.includes('*'), 'img-src must not allow every origin');
    assert.ok(!img.includes('https:'), "img-src must not use the scheme-only source 'https:'");
});
