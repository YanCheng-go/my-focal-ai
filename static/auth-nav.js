// Shared auth + user dropdown for nav bar.
// Requires: @supabase/supabase-js loaded, user-menu-container dropdown markup in nav.
(async function() {
    var isLoggedIn = false;

    // --- Toggle user dropdown ---
    window.toggleUserMenu = function() {
        var loggedOutMenu = document.getElementById('user-dropdown-loggedout');
        var loggedInMenu = document.getElementById('user-dropdown-loggedin');
        if (!loggedOutMenu || !loggedInMenu) return;

        var menu = isLoggedIn ? loggedInMenu : loggedOutMenu;
        var other = isLoggedIn ? loggedOutMenu : loggedInMenu;
        other.classList.add('hidden');
        menu.classList.toggle('hidden');
    };

    // --- Click-outside to close ---
    document.addEventListener('click', function(e) {
        var container = document.getElementById('user-menu-container');
        if (!container || container.contains(e.target)) return;
        var loggedOutMenu = document.getElementById('user-dropdown-loggedout');
        var loggedInMenu = document.getElementById('user-dropdown-loggedin');
        if (loggedOutMenu) loggedOutMenu.classList.add('hidden');
        if (loggedInMenu) loggedInMenu.classList.add('hidden');
    });

    // --- Sign in ---
    window.handleSignIn = async function() {
        var errEl = document.getElementById('login-error');
        var email = (document.getElementById('login-email') || {}).value;
        var password = (document.getElementById('login-password') || {}).value;
        if (!email || !password) {
            if (errEl) {
                errEl.textContent = 'Enter email and password.';
                errEl.className = 'text-xs text-red-500 mb-2';
                errEl.classList.remove('hidden');
            }
            return;
        }
        try {
            var result = await window._sb.auth.signInWithPassword({ email: email, password: password });
            if (result.error) throw result.error;
            location.reload();
        } catch (e) {
            if (errEl) {
                errEl.textContent = e.message || 'Sign-in failed.';
                errEl.className = 'text-xs text-red-500 mb-2';
                errEl.classList.remove('hidden');
            }
        }
    };

    // --- Sign up ---
    window.handleSignUp = async function() {
        var errEl = document.getElementById('login-error');
        var email = (document.getElementById('login-email') || {}).value;
        var password = (document.getElementById('login-password') || {}).value;
        if (!email || !password) {
            if (errEl) {
                errEl.textContent = 'Enter email and password.';
                errEl.className = 'text-xs text-red-500 mb-2';
                errEl.classList.remove('hidden');
            }
            return;
        }
        try {
            var result = await window._sb.auth.signUp({ email: email, password: password });
            if (result.error) throw result.error;
            if (errEl) {
                errEl.textContent = 'Check your email to confirm your account.';
                errEl.className = 'text-xs text-green-600 dark:text-green-400 mb-2';
                errEl.classList.remove('hidden');
            }
        } catch (e) {
            if (errEl) {
                errEl.textContent = e.message || 'Sign-up failed.';
                errEl.className = 'text-xs text-red-500 mb-2';
                errEl.classList.remove('hidden');
            }
        }
    };

    // --- Toggle sign-in / sign-up mode ---
    var isSignUpMode = false;
    window.toggleAuthMode = function(e) {
        if (e) e.preventDefault();
        isSignUpMode = !isSignUpMode;
        var title = document.getElementById('auth-title');
        var btn = document.getElementById('auth-submit');
        var link = document.getElementById('auth-toggle-link');
        var toggleText = document.getElementById('auth-toggle-text');
        var errEl = document.getElementById('login-error');
        if (errEl) errEl.classList.add('hidden');
        if (isSignUpMode) {
            if (title) title.textContent = 'Create an account';
            if (btn) { btn.textContent = 'Sign Up'; btn.setAttribute('onclick', 'handleSignUp()'); }
            if (toggleText) toggleText.innerHTML = 'Already have an account? <a href="#" onclick="toggleAuthMode(event)" class="text-blue-600 dark:text-blue-400 hover:underline">Sign in</a>';
        } else {
            if (title) title.textContent = 'Sign in to MyFocalAI';
            if (btn) { btn.textContent = 'Sign In'; btn.setAttribute('onclick', 'handleSignIn()'); }
            if (toggleText) toggleText.innerHTML = 'Don\'t have an account? <a href="#" onclick="toggleAuthMode(event)" class="text-blue-600 dark:text-blue-400 hover:underline">Sign up</a>';
        }
    };

    // --- Sign out ---
    window.handleSignOut = async function(e) {
        if (e) e.preventDefault();
        if (window._sb) {
            await window._sb.auth.signOut();
        }
        location.reload();
    };

    // --- Backwards compat: hide old #auth-indicator if present ---
    var oldEl = document.getElementById('auth-indicator');
    if (oldEl) oldEl.classList.add('hidden');

    // --- Session detection ---
    var container = document.getElementById('user-menu-container');
    var iconBtn = document.getElementById('user-icon-btn');
    var emailEl = document.getElementById('user-email');

    try {
        var config = window.getConfig ? await window.getConfig() : await fetch('config.json').then(function(r) { return r.ok ? r.json() : {}; });
        if (!config.supabase_url || !config.supabase_anon_key) {
            // No Supabase config — hide user menu (Sources nav link handles admin access)
            if (container) container.classList.add('hidden');
            return;
        }

        var sb = window._sb || supabase.createClient(config.supabase_url, config.supabase_anon_key);
        window._sb = sb;

        var result = await sb.auth.getSession();
        var session = result.data.session;

        if (session) {
            isLoggedIn = true;
            // Color the user icon blue to indicate logged-in state
            if (iconBtn) {
                iconBtn.classList.remove('text-gray-400');
                iconBtn.classList.add('text-blue-600', 'dark:text-blue-400');
            }
            // Populate email display
            if (emailEl) {
                var safeEmail = session.user.email
                    .replace(/&/g, '&amp;')
                    .replace(/</g, '&lt;')
                    .replace(/>/g, '&gt;')
                    .replace(/"/g, '&quot;');
                emailEl.innerHTML = safeEmail;
            }
        } else {
            isLoggedIn = false;
            // Keep default gray icon color
            if (iconBtn) {
                iconBtn.classList.remove('text-blue-600', 'dark:text-blue-400');
                iconBtn.classList.add('text-gray-400');
            }
        }
    } catch (e) {
        // Supabase not available — hide user menu
        if (container) container.classList.add('hidden');
    }
})();
