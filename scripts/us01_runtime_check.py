import os
import re

os.environ.setdefault('SECRET_KEY', 'test-secret')
os.environ.setdefault('DEFAULT_USERNAME', 'admin')
os.environ.setdefault('DEFAULT_PASSWORD', 'admin')
os.environ.setdefault('FLASK_ENV', 'production')

from app import app

def main():
    ext = getattr(app, 'extensions', {}) or {}
    csrf_active = bool(ext.get('csrf'))
    print(f'CSRF active: {csrf_active}')

    with app.test_client() as c:
        # 1) POST without CSRF
        r1 = c.post('/_csrf_ping')
        print('POST /_csrf_ping (no CSRF) ->', r1.status_code)

        # Generate a Set-Cookie header by saving session in a request context
        from flask import session as flask_session, make_response
        with app.test_request_context('/'):
            flask_session['probe'] = '1'
            resp = make_response('ok')
            app.session_interface.save_session(app, flask_session, resp)
            sc_list = resp.headers.getlist('Set-Cookie')
            print('Set-Cookie headers (generated):')
            for sc in sc_list:
                print('  ', sc)
            full_cookie = '\n'.join(sc_list)
            print('Cookie flags -> Secure:', ('Secure' in full_cookie), 'HttpOnly:', ('HttpOnly' in full_cookie), 'SameSite=Lax:', ('SameSite=Lax' in full_cookie))

        # 3) CSP header from GET /login (ensures a rendered page)
        r_login = c.get('/login')
        csp = r_login.headers.get('Content-Security-Policy')
        print('CSP header:', csp)

        # Extract meta token from login page
        token = None
        m = re.search(rb'<meta name="csrf-token" content="([^"]+)">', r_login.data)
        if m:
            token = m.group(1).decode()
        print('Meta CSRF token present:', bool(token))

        # Check hidden input presence on login form
        has_hidden_input = bool(re.search(rb'<input[^>]+name=["\']csrf_token["\']', r_login.data))
        print('Login form has hidden csrf input:', has_hidden_input)

        if token:
            r2 = c.post('/_csrf_ping', headers={'X-CSRFToken': token})
            print('POST /_csrf_ping with CSRF ->', r2.status_code, r2.json)

if __name__ == '__main__':
    main()


