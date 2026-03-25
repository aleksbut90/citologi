// Функция для проверки авторизации
function checkAuth() {
    return fetch('/api/check_auth', {
        method: 'GET',
        credentials: 'include'
    })
    .then(response => {
        if (response.ok) {
            return response.json();
        } else {
            throw new Error('Unauthorized');
        }
    })
    .catch(error => {
        console.error('Ошибка проверки авторизации:', error);
        // Перенаправляем на страницу авторизации
        window.location.href = '/authorization.html';
        return null;
    });
}

// Функция для выхода из системы
function logout() {
    return fetch('/api/logout', {
        method: 'POST',
        credentials: 'include'
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === 'success') {
            // Перенаправляем на страницу авторизации
            window.location.href = '/authorization.html';
        } else {
            console.error('Ошибка выхода:', data.message);
        }
    })
    .catch(error => {
        console.error('Ошибка выхода из системы:', error);
        // В любом случае перенаправляем на авторизацию
        window.location.href = '/authorization.html';
    });
}

// Функция для инициализации проверки авторизации на странице
function initAuthCheck() {
    // Проверяем авторизацию при загрузке страницы
    checkAuth().then(userData => {
        if (userData && userData.status === 'success') {
            console.log('Пользователь авторизован:', userData.user);
            // Можно добавить отображение информации о пользователе
            displayUserInfo(userData.user);
        }
    });
}

// Функция для отображения информации о пользователе
function displayUserInfo(user) {
    // Находим элемент для отображения информации о пользователе
    const userInfoElement = document.getElementById('user-info');
    if (userInfoElement && user) {
        userInfoElement.innerHTML = `
            <span class="user-name">${user.fio || user.login}</span>
            <button onclick="logout()" class="logout-btn">Выйти</button>
        `;
    }
}

// Функция для добавления обработчика выхода
function addLogoutHandler() {
    const logoutButtons = document.querySelectorAll('.logout-btn, [data-logout]');
    logoutButtons.forEach(button => {
        button.addEventListener('click', (e) => {
            e.preventDefault();
            logout();
        });
    });
}

// Инициализация при загрузке страницы
document.addEventListener('DOMContentLoaded', function() {
    // Проверяем, что мы не на странице авторизации
    if (!window.location.pathname.includes('authorization.html')) {
        initAuthCheck();
        addLogoutHandler();
    }
});

// Экспортируем функции для использования в других скриптах
window.authUtils = {
    checkAuth,
    logout,
    initAuthCheck,
    displayUserInfo
}; 