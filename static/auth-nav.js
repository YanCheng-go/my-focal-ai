// Shared auth indicator for nav bar.
// Requires: @supabase/supabase-js loaded, element with id="auth-indicator" in nav.
(async function() {
    var el = document.getElementById('auth-indicator');
    if (!el) return;
    try {
        var resp = await fetch('config.json');
        if (!resp.ok) return;
        var config = await resp.json();
        if (!config.supabase_url || !config.supabase_anon_key) return;

        var sb = window._sb || supabase.createClient(config.supabase_url, config.supabase_anon_key);
        window._sb = sb;
        var result = await sb.auth.getSession();
        var session = result.data.session;

        if (session) {
            el.innerHTML = '<span class="text-gray-400 dark:text-gray-500">' +
                session.user.email.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;') +
                '</span> <a href="#" class="text-gray-400 hover:text-red-500 dark:hover:text-red-400 ml-1" id="auth-logout">Logout</a>';
            el.classList.remove('hidden');
            document.getElementById('auth-logout').onclick = async function(e) {
                e.preventDefault();
                await sb.auth.signOut();
                location.reload();
            };
        } else {
            el.innerHTML = '<a href="admin.html" class="text-blue-500 hover:text-blue-600 dark:text-blue-400 dark:hover:text-blue-300">Sign in</a>';
            el.classList.remove('hidden');
        }
    } catch (e) {
        // Supabase not available — stay hidden
    }
})();
