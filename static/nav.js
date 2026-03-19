// Shared nav bar injector for static pages.
// Usage: <nav id="main-nav" data-active="dashboard"></nav>
// Then include <script src="nav.js"></script> in the <body>.
(function() {
    var nav = document.getElementById('main-nav');
    if (!nav) return;
    var active = nav.dataset.active || '';

    var inactiveLink = 'text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200';
    var activeLink = 'text-blue-600 dark:text-blue-400 font-medium';

    function cls(page) { return active === page ? activeLink : inactiveLink; }

    // Theme
    window.setTheme = function(mode) {
        if (mode === 'dark') { localStorage.setItem('theme', 'dark'); document.documentElement.classList.add('dark'); }
        else if (mode === 'light') { localStorage.setItem('theme', 'light'); document.documentElement.classList.remove('dark'); }
        else { localStorage.removeItem('theme'); document.documentElement.classList.toggle('dark', window.matchMedia('(prefers-color-scheme: dark)').matches); }
        _updateThemeButtons();
    };
    function _updateThemeButtons() {
        var t = localStorage.getItem('theme');
        ['light', 'system', 'dark'].forEach(function(m) {
            var el = document.getElementById('theme-' + m);
            if (!el) return;
            el.className = 'p-1.5 rounded cursor-pointer ' + ((m === 'system' && !t) || (t === m) ? 'text-blue-600 dark:text-blue-400' : 'text-gray-400 hover:text-gray-600 dark:hover:text-gray-300');
        });
    }

    function badgeSpan(id) {
        return '<span id="' + id + '" class="hidden bg-red-500 text-white text-[10px] rounded-full px-1 min-w-[14px] text-center leading-4 font-bold"></span>';
    }

    // Hamburger icon SVGs
    var menuIcon = '<svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M4 6h16M4 12h16M4 18h16"/></svg>';
    var closeIcon = '<svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12"/></svg>';

    // Nav links: Feeds, Admin, Leaderboard, Trends, CCC, Events, About
    var links =
        '<a href="index.html" class="inline-flex items-center gap-1 py-1 ' + cls('dashboard') + '">Feeds ' + badgeSpan('badge-dashboard') + '</a>' +
        '<a href="admin.html" class="py-1 ' + cls('admin') + '">Admin</a>' +
        '<a href="leaderboard.html" class="py-1 ' + cls('leaderboard') + '">Leaderboard</a>' +
        '<a href="trends.html" class="py-1 ' + cls('trends') + '">Trends</a>' +
        '<a href="ccc.html" class="inline-flex items-center gap-1 py-1 ' + cls('ccc') + '">CCC ' + badgeSpan('badge-ccc') + '</a>' +
        '<a href="events.html" class="py-1 ' + cls('events') + '">Events</a>' +
        '<a href="about.html" class="py-1 ' + cls('about') + '">About</a>';

    // Mobile links with larger touch targets
    var mobileLink = 'py-2 px-2 rounded-md hover:bg-gray-50 dark:hover:bg-neutral-800';
    var mobileLinks =
        '<a href="index.html" class="inline-flex items-center gap-1 ' + mobileLink + ' ' + cls('dashboard') + '">Feeds ' + badgeSpan('badge-dashboard-m') + '</a>' +
        '<a href="admin.html" class="' + mobileLink + ' ' + cls('admin') + '">Admin</a>' +
        '<a href="leaderboard.html" class="' + mobileLink + ' ' + cls('leaderboard') + '">Leaderboard</a>' +
        '<a href="trends.html" class="' + mobileLink + ' ' + cls('trends') + '">Trends</a>' +
        '<a href="ccc.html" class="inline-flex items-center gap-1 ' + mobileLink + ' ' + cls('ccc') + '">CCC ' + badgeSpan('badge-ccc-m') + '</a>' +
        '<a href="events.html" class="' + mobileLink + ' ' + cls('events') + '">Events</a>' +
        '<a href="about.html" class="' + mobileLink + ' ' + cls('about') + '">About</a>' +
        '<a href="https://buymeacoffee.com/maverickmiaow" target="_blank" rel="noopener noreferrer" class="inline-flex items-center gap-1 ' + mobileLink + ' text-gray-400 hover:text-yellow-500 dark:hover:text-yellow-400">&#x2615; Support</a>';

    var rightSide =
        '<a href="https://buymeacoffee.com/maverickmiaow" target="_blank" rel="noopener noreferrer" class="hidden sm:inline-flex items-center gap-1 px-2 py-1 text-xs text-gray-400 hover:text-yellow-500 dark:hover:text-yellow-400" title="Support the Developer">&#x2615; Support</a>' +
        '<button onclick="setTheme(\'light\')" id="theme-light" class="p-1.5 rounded cursor-pointer" title="Light"><svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z"/></svg></button>' +
        '<button onclick="setTheme(\'system\')" id="theme-system" class="p-1.5 rounded cursor-pointer" title="System"><svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"/></svg></button>' +
        '<button onclick="setTheme(\'dark\')" id="theme-dark" class="p-1.5 rounded cursor-pointer" title="Dark"><svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z"/></svg></button>' +
        '<a href="https://github.com/YanCheng-go/my-focal-ai" target="_blank" rel="noopener" class="p-1.5 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300" title="GitHub"><svg class="w-4 h-4" viewBox="0 0 16 16" fill="currentColor"><path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"/></svg></a>' +
        '<div class="w-px h-4 bg-gray-200 dark:bg-neutral-700 mx-1"></div>' +
        '<div class="relative" id="user-menu-container">' +
            '<button onclick="toggleUserMenu()" class="p-1.5 rounded cursor-pointer text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-neutral-800" title="Account" id="user-icon-btn">' +
                '<svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"/></svg>' +
            '</button>' +
            '<div id="user-dropdown-loggedout" class="hidden absolute right-0 top-full mt-2 w-72 bg-white dark:bg-neutral-900 border border-gray-200 dark:border-neutral-700 rounded-lg shadow-xl z-50">' +
                '<div class="p-4">' +
                    '<h3 id="auth-title" class="text-sm font-semibold text-gray-900 dark:text-white mb-1">Sign in to MyFocalAI</h3>' +
                    '<p class="text-xs text-gray-500 dark:text-gray-400 mb-3">Manage your personal feed sources</p>' +
                    '<input type="email" id="login-email" placeholder="Email" class="w-full mb-2 px-3 py-2 rounded-md bg-gray-50 dark:bg-neutral-800 border border-gray-200 dark:border-neutral-700 text-sm outline-none focus:border-blue-400 dark:focus:border-blue-500 text-gray-900 dark:text-gray-200">' +
                    '<input type="password" id="login-password" placeholder="Password" class="w-full mb-3 px-3 py-2 rounded-md bg-gray-50 dark:bg-neutral-800 border border-gray-200 dark:border-neutral-700 text-sm outline-none focus:border-blue-400 dark:focus:border-blue-500 text-gray-900 dark:text-gray-200">' +
                    '<p id="login-error" class="hidden text-xs text-red-500 mb-2"></p>' +
                    '<button id="auth-submit" onclick="handleSignIn()" class="w-full py-2 rounded-md bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium cursor-pointer">Sign In</button>' +
                    '<p class="text-xs text-center mt-3 text-gray-500 dark:text-gray-400" id="auth-toggle-text">Don\'t have an account? <a href="#" onclick="toggleAuthMode(event)" class="text-blue-600 dark:text-blue-400 hover:underline">Sign up</a></p>' +
                '</div>' +
            '</div>' +
            '<div id="user-dropdown-loggedin" class="hidden absolute right-0 top-full mt-2 w-56 bg-white dark:bg-neutral-900 border border-gray-200 dark:border-neutral-700 rounded-lg shadow-xl z-50">' +
                '<div class="p-3 border-b border-gray-100 dark:border-neutral-800">' +
                    '<p class="text-sm font-medium text-gray-900 dark:text-white truncate" id="user-email"></p>' +
                    '<p class="text-xs text-gray-400">Signed in</p>' +
                '</div>' +
                '<div class="py-1">' +
                    '<a href="#" onclick="handleSignOut(event)" class="flex items-center gap-2 px-3 py-2 text-sm text-red-600 dark:text-red-400 hover:bg-gray-50 dark:hover:bg-neutral-800">' +
                        '<svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"/></svg>' +
                        'Sign Out' +
                    '</a>' +
                '</div>' +
            '</div>' +
        '</div>';

    nav.innerHTML =
        '<div class="max-w-4xl mx-auto px-5 py-3">' +
        '<div class="flex items-center gap-x-4 gap-y-2">' +
            // Logo
            '<a href="index.html" class="flex items-center gap-2 shrink-0"><img src="logo.svg" alt="MyFocalAI" class="w-7 h-7 rounded-lg"><span class="text-lg font-bold text-gray-900 dark:text-white">MyFocalAI</span></a>' +
            // Desktop nav links (hidden on mobile)
            '<div class="hidden sm:flex flex-wrap items-center gap-x-3 gap-y-1 text-sm" id="nav-links-desktop">' + links + '</div>' +
            // Right side (always visible)
            '<div class="flex items-center gap-1 ml-auto">' + rightSide +
                // Hamburger button (visible on mobile only)
                '<div class="w-px h-4 bg-gray-200 dark:bg-neutral-700 mx-1 sm:hidden"></div>' +
                '<button onclick="toggleMobileMenu()" class="sm:hidden p-1.5 rounded cursor-pointer text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-neutral-800" title="Menu" id="hamburger-btn">' + menuIcon + '</button>' +
            '</div>' +
        '</div>' +
        // Mobile nav links (hidden by default, toggled by hamburger)
        '<div class="hidden sm:hidden flex-col gap-1 pt-3 pb-1 border-t border-gray-100 dark:border-neutral-800 mt-3 text-sm" id="nav-links-mobile">' + mobileLinks + '</div>' +
        '</div>';

    _updateThemeButtons();

    // Mobile menu toggle
    window.toggleMobileMenu = function() {
        var mobile = document.getElementById('nav-links-mobile');
        var btn = document.getElementById('hamburger-btn');
        if (!mobile) return;
        var isOpen = !mobile.classList.contains('hidden');
        if (isOpen) {
            mobile.classList.add('hidden');
            mobile.classList.remove('flex');
            btn.innerHTML = menuIcon;
        } else {
            mobile.classList.remove('hidden');
            mobile.classList.add('flex');
            btn.innerHTML = closeIcon;
        }
    };
})();
