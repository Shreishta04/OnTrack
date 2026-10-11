"""SSRF guard: the server must only ever download from public websites,
including after redirects. No network is used: names are looked up by a fake
resolver, and downloads by a fake raw_get."""

import pytest

from extractor import UnsafeURL, check_public_url, extract, guarded_get, make_fetcher

# A fake "phone book": website name -> addresses it points to.
DNS = {
    "shop.example": ["93.184.216.34"],
    "cdn.example": ["151.101.1.1"],
    "localhost": ["127.0.0.1"],
    "admin.internal": ["10.0.0.5"],
    "sneaky.example": ["93.184.216.34", "192.168.1.1"],     # one public, one private
    "rebind.example": ["::ffff:10.0.0.1"],                  # IPv6 wrapper around a private IPv4
    "2852039166": ["169.254.169.254"],                      # the cloud-secrets address written as a number
    "169.254.169.254": ["169.254.169.254"],
    "::1": ["::1"],
}


def resolve(host, port, **kwargs):
    if host not in DNS:
        import socket
        raise socket.gaierror("not found")
    return [(2, 1, 6, "", (ip, port)) for ip in DNS[host]]


@pytest.mark.parametrize("url", [
    "http://localhost/admin",
    "http://169.254.169.254/latest/meta-data/",
    "http://2852039166/",
    "http://admin.internal/",
    "http://[::1]/",
    "http://sneaky.example/",
    "http://rebind.example/",
    "https://shop.example:8443/",      # not a normal web port
    "file:///etc/passwd",
    "ftp://shop.example/",
])
def test_unsafe_links_are_refused(url):
    with pytest.raises(UnsafeURL):
        check_public_url(url, resolve)


def test_public_link_is_allowed_and_its_address_returned():
    assert check_public_url("https://shop.example/p/1", resolve) == "93.184.216.34"


def test_unknown_name_is_a_network_error_not_unsafe():
    with pytest.raises(ConnectionError):
        check_public_url("https://no-such-shop.example/", resolve)


def fake_web(pages):
    """pages: url -> (status, location, text). Records which address each download used."""
    used = []

    def raw_get(url, ip, timeout):
        used.append((url, ip))
        return pages[url]
    return raw_get, used


def test_redirect_to_a_private_address_is_refused():
    """A public page bouncing the server to an internal one: the hop is checked
    before anything is downloaded from it."""
    raw_get, used = fake_web({"https://shop.example/p": (302, "http://admin.internal/", "")})
    with pytest.raises(UnsafeURL):
        guarded_get(raw_get, resolve)("https://shop.example/p", 20)
    assert [u for u, _ in used] == ["https://shop.example/p"]         # never contacted admin.internal


def test_public_redirects_are_followed_and_each_download_uses_the_checked_address():
    raw_get, used = fake_web({
        "https://shop.example/short": (301, "/real-page", ""),                  # relative Location
        "https://shop.example/real-page": (302, "https://cdn.example/p", ""),
        "https://cdn.example/p": (200, None, "<html>product</html>"),
    })
    page = guarded_get(raw_get, resolve)("https://shop.example/short", 20)
    assert page.status == 200 and page.url == "https://cdn.example/p"
    assert used == [("https://shop.example/short", "93.184.216.34"),
                    ("https://shop.example/real-page", "93.184.216.34"),
                    ("https://cdn.example/p", "151.101.1.1")]                 # pinned, not looked up again


def test_endless_redirects_give_up():
    raw_get, _ = fake_web({"https://shop.example/a": (302, "/a", "")})
    with pytest.raises(ConnectionError, match="too many"):
        guarded_get(raw_get, resolve)("https://shop.example/a", 20)


def test_real_fetcher_refuses_localhost_without_connecting():
    """The real curl-based fetcher, end to end: the item says why, nothing is downloaded."""
    p = extract("http://localhost/admin", make_fetcher())
    assert not p.ok and "won't open this link" in p.error