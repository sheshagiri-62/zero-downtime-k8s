let token = localStorage.getItem('token');
let products = [];
let cart = [];

// Initialize
async function init() {
    updateNav();
    await fetchVersion();
    await loadProducts();
    if (token) await loadCart();
}

function updateNav() {
    if (token) {
        document.getElementById('nav-login').style.display = 'none';
        document.getElementById('nav-logout').style.display = 'inline';
        document.getElementById('nav-orders').style.display = 'inline';
    } else {
        document.getElementById('nav-login').style.display = 'inline';
        document.getElementById('nav-logout').style.display = 'none';
        document.getElementById('nav-orders').style.display = 'none';
    }
}

function showPage(pageId) {
    document.querySelectorAll('.page').forEach(p => p.style.display = 'none');
    document.getElementById(pageId + '-page').style.display = 'block';
    
    if (pageId === 'orders' && token) {
        loadOrders();
    }
}

async function fetchVersion() {
    try {
        const res = await fetch('/version');
        const data = await res.json();
        document.getElementById('version-text').innerText = data.version;
    } catch (e) {
        console.error('Failed to fetch version', e);
    }
}

async function loadProducts() {
    const res = await fetch('/api/products');
    products = await res.json();
    const grid = document.getElementById('product-grid');
    grid.innerHTML = '';
    products.forEach(p => {
        grid.innerHTML += `
            <div class="product-card">
                <img src="${p.image}" alt="${p.name}">
                <h3>${p.name}</h3>
                <p>$${p.price.toFixed(2)}</p>
                <button onclick="addToCart(${p.id})">Add to Cart</button>
            </div>
        `;
    });
}

async function loadCart() {
    if (!token) return;
    const res = await fetch('/api/cart', { headers: { 'Authorization': 'Bearer ' + token } });
    if (res.ok) {
        cart = await res.json();
        renderCart();
    }
}

async function addToCart(id) {
    if (!token) {
        alert("Please login first!");
        showPage('login');
        return;
    }
    await fetch('/api/cart', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token },
        body: JSON.stringify({ product_id: id })
    });
    cart.push(id);
    renderCart();
}

function renderCart() {
    document.getElementById('cart-count').innerText = cart.length;
    const cartItems = document.getElementById('cart-items');
    let total = 0;
    cartItems.innerHTML = '';
    if (cart.length === 0) {
        cartItems.innerHTML = '<p>Cart is empty.</p>';
    } else {
        cart.forEach(id => {
            const p = products.find(x => x.id === id);
            if (p) {
                total += p.price;
                cartItems.innerHTML += `<p>${p.name} - $${p.price.toFixed(2)}</p>`;
            }
        });
    }
    document.getElementById('cart-total').innerText = total.toFixed(2);
}

async function checkout() {
    if (cart.length === 0) return alert('Cart is empty!');
    let total = parseFloat(document.getElementById('cart-total').innerText);
    const res = await fetch('/api/orders', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token },
        body: JSON.stringify({ items: cart, total: total })
    });
    if (res.ok) {
        alert('Order placed successfully!');
        cart = []; // clear local cart
        renderCart();
        showPage('orders');
    }
}

async function loadOrders() {
    const res = await fetch('/api/orders', { headers: { 'Authorization': 'Bearer ' + token } });
    const orders = await res.json();
    const list = document.getElementById('orders-list');
    list.innerHTML = '';
    orders.forEach(o => {
        list.innerHTML += `
            <div class="order-card">
                <p><strong>Order #${o.id}</strong> - Date: ${o.created_at}</p>
                <p>Total: $${o.total.toFixed(2)}</p>
                <p><span class="version-tag">Processed by v${o.app_version}</span></p>
            </div>
        `;
    });
}

async function login() {
    const email = document.getElementById('email').value;
    const password = document.getElementById('password').value;
    const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password })
    });
    if (res.ok) {
        const data = await res.json();
        token = data.token;
        localStorage.setItem('token', token);
        document.getElementById('auth-msg').innerText = "Logged in!";
        document.getElementById('auth-msg').style.color = "green";
        init();
        showPage('home');
    } else {
        document.getElementById('auth-msg').innerText = "Invalid credentials";
        document.getElementById('auth-msg').style.color = "red";
    }
}

async function register() {
    const email = document.getElementById('email').value;
    const password = document.getElementById('password').value;
    const res = await fetch('/api/auth/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password })
    });
    if (res.ok) {
        document.getElementById('auth-msg').innerText = "Registered! Please log in.";
        document.getElementById('auth-msg').style.color = "green";
    } else {
        const data = await res.json();
        document.getElementById('auth-msg').innerText = data.detail || "Registration failed";
        document.getElementById('auth-msg').style.color = "red";
    }
}

function logout() {
    token = null;
    cart = [];
    localStorage.removeItem('token');
    updateNav();
    renderCart();
    showPage('home');
}

init();
