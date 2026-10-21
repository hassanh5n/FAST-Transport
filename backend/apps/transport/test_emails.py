"""Self-checks for email rendering and the Brevo backend. No database needed."""
from django.contrib.auth.models import User
from django.core.mail import EmailMultiAlternatives
from django.test import SimpleTestCase, override_settings

from apps.transport.emails import display_name, render_email
from config.brevo_backend import BrevoAPIEmailBackend


class EmailRenderingTests(SimpleTestCase):
    def test_user_content_is_html_escaped(self):
        _, html = render_email(heading="<script>x</script>", paragraphs=["<img src=x onerror=alert(1)>"],
                               name="<b>Eve</b>", button_url='https://a.b/"onclick="x')
        self.assertNotIn("<script>", html)
        self.assertNotIn("<img", html)
        self.assertNotIn("<b>Eve</b>", html)
        self.assertNotIn('"onclick="', html)

    def test_greets_by_full_name_with_username_fallback(self):
        self.assertEqual(display_name(User(username="k230769", first_name="Hassan", last_name="Nafees")), "Hassan Nafees")
        self.assertEqual(display_name(User(username="k230769")), "k230769")


@override_settings(DEFAULT_FROM_EMAIL='"Fleetcentric.ai" <noreply@example.com>', BREVO_API_KEY="x")
class BrevoPayloadTests(SimpleTestCase):
    def test_sender_name_has_no_quotes_and_html_matches_smtp(self):
        msg = EmailMultiAlternatives("Subj", "text", None, ["a@b.c"], reply_to=["r@b.c"])
        msg.attach_alternative("<p>hi</p>", "text/html")
        p = BrevoAPIEmailBackend()._payload(msg)
        self.assertEqual(p["sender"], {"name": "Fleetcentric.ai", "email": "noreply@example.com"})
        self.assertEqual(p["to"], [{"email": "a@b.c"}])
        self.assertEqual(p["replyTo"], {"email": "r@b.c"})
        self.assertEqual((p["textContent"], p["htmlContent"]), ("text", "<p>hi</p>"))
