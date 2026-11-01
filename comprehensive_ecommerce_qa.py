"""Educational e-commerce QA example. Run: python comprehensive_ecommerce_qa.py"""
from dataclasses import dataclass, field
import re
import unittest

@dataclass
class Product:
    product_id: str
    name: str
    price: float
    stock: int
    active: bool = True
    def __post_init__(self):
        if not self.product_id.strip() or not self.name.strip():
            raise ValueError("Product ID and name are required")
        if self.price < 0 or self.stock < 0:
            raise ValueError("Price and stock cannot be negative")

class Catalog:
    def __init__(self): self.products = {}
    def add(self, product):
        if product.product_id in self.products: raise ValueError("Duplicate ID")
        self.products[product.product_id] = product
    def get(self, product_id):
        p = self.products.get(product_id)
        if p is None or not p.active: raise KeyError("Product not found")
        return p
    def search(self, keyword):
        term = keyword.strip().casefold()
        return [p for p in self.products.values() if p.active and term and term in p.name.casefold()]

@dataclass
class Cart:
    items: dict = field(default_factory=dict)
    def add(self, product, quantity=1):
        if not product.active or not isinstance(quantity, int) or quantity <= 0:
            raise ValueError("Invalid product or quantity")
        old = self.items.get(product.product_id, (product, 0))[1]
        if old + quantity > product.stock: raise ValueError("Insufficient stock")
        self.items[product.product_id] = (product, old + quantity)
    def update(self, product_id, quantity):
        if product_id not in self.items: raise KeyError("Item not in cart")
        product = self.items[product_id][0]
        if quantity <= 0: self.remove(product_id)
        elif quantity > product.stock: raise ValueError("Insufficient stock")
        else: self.items[product_id] = (product, quantity)
    def remove(self, product_id):
        if product_id not in self.items: raise KeyError("Item not in cart")
        del self.items[product_id]
    def total(self):
        return round(sum(p.price*q for p, q in self.items.values()), 2)
    def clear(self): self.items.clear()

def validate_registration(email, password):
    valid = isinstance(email, str) and re.fullmatch(r"[^@\\s]+@[^@\\s]+\\.[^@\\s]+", email.strip())
    return bool(valid and isinstance(password, str) and len(password) >= 8)

class Inventory:
    def __init__(self): self.stock = {}
    def set_stock(self, product_id, quantity):
        if quantity < 0: raise ValueError("Negative stock")
        self.stock[product_id] = quantity
    def reserve(self, product_id, quantity):
        if quantity <= 0 or quantity > self.stock.get(product_id, 0):
            raise ValueError("Invalid quantity or insufficient stock")
        self.stock[product_id] -= quantity

class FakePayment:
    def charge(self, amount, token):
        if amount <= 0 or not token: return {"success": False, "reason": "invalid"}
        if token == "decline": return {"success": False, "reason": "declined"}
        return {"success": True, "transaction_id": "TEST-TXN-001"}

class Checkout:
    def __init__(self, inventory, gateway):
        self.inventory, self.gateway, self.orders = inventory, gateway, {}
    def place_order(self, cart, token, request_id):
        if request_id in self.orders: return self.orders[request_id]
        if not cart.items: raise ValueError("Empty cart")
        for pid, (_, qty) in cart.items.items():
            if self.inventory.stock.get(pid, 0) < qty: raise ValueError("Insufficient stock")
        payment = self.gateway.charge(cart.total(), token)
        if not payment["success"]: return {"status": "payment_failed"}
        for pid, (_, qty) in cart.items.items(): self.inventory.reserve(pid, qty)
        order = {"request_id": request_id, "status": "confirmed",
                 "total": cart.total(), "transaction_id": payment["transaction_id"]}
        self.orders[request_id] = order
        cart.clear()
        return order

class TestRegistration(unittest.TestCase):
    def test_valid(self): self.assertTrue(validate_registration("a@example.com", "password123"))
    def test_invalid_email(self): self.assertFalse(validate_registration("bad", "password123"))
    def test_short_password(self): self.assertFalse(validate_registration("a@example.com", "123"))

class TestCatalog(unittest.TestCase):
    def setUp(self):
        self.c = Catalog()
        self.c.add(Product("P1", "Wireless Headphones", 120, 8))
    def test_retrieve(self): self.assertEqual(self.c.get("P1").name, "Wireless Headphones")
    def test_duplicate(self):
        with self.assertRaises(ValueError): self.c.add(Product("P1", "Other", 2, 1))
    def test_search(self): self.assertEqual(len(self.c.search("HEAD")), 1)
    def test_missing(self):
        with self.assertRaises(KeyError): self.c.get("missing")

class TestCart(unittest.TestCase):
    def setUp(self): self.cart, self.p = Cart(), Product("P2", "Keyboard", 50, 5)
    def test_add_total(self):
        self.cart.add(self.p, 2); self.assertEqual(self.cart.total(), 100)
    def test_zero_quantity(self):
        with self.assertRaises(ValueError): self.cart.add(self.p, 0)
    def test_stock_limit(self):
        with self.assertRaises(ValueError): self.cart.add(self.p, 6)
    def test_update_remove(self):
        self.cart.add(self.p); self.cart.update("P2", 3)
        self.assertEqual(self.cart.total(), 150)
        self.cart.remove("P2"); self.assertEqual(self.cart.total(), 0)

class TestInventory(unittest.TestCase):
    def setUp(self): self.inv = Inventory(); self.inv.set_stock("P3", 3)
    def test_reserve(self):
        self.inv.reserve("P3", 2); self.assertEqual(self.inv.stock["P3"], 1)
    def test_oversell(self):
        with self.assertRaises(ValueError): self.inv.reserve("P3", 4)
    def test_negative_stock(self):
        with self.assertRaises(ValueError): self.inv.set_stock("P3", -1)

class TestCheckoutIntegration(unittest.TestCase):
    def setUp(self):
        self.p = Product("P4", "Monitor", 200, 4)
        self.cart = Cart(); self.cart.add(self.p)
        self.inv = Inventory(); self.inv.set_stock("P4", 4)
        self.service = Checkout(self.inv, FakePayment())
    def test_success(self):
        order = self.service.place_order(self.cart, "sandbox-token", "R1")
        self.assertEqual(order["status"], "confirmed")
        self.assertEqual(self.inv.stock["P4"], 3)
        self.assertEqual(self.cart.total(), 0)
    def test_declined(self):
        result = self.service.place_order(self.cart, "decline", "R2")
        self.assertEqual(result["status"], "payment_failed")
        self.assertEqual(self.inv.stock["P4"], 4)
    def test_idempotent_retry(self):
        first = self.service.place_order(self.cart, "sandbox-token", "R3")
        retry = Cart(); retry.add(self.p)
        second = self.service.place_order(retry, "sandbox-token", "R3")
        self.assertEqual(first, second)
        self.assertEqual(len(self.service.orders), 1)

if __name__ == "__main__":
    unittest.main(verbosity=2)
