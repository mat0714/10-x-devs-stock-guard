from django.contrib.auth.models import User
from django.test import TestCase

PASSWORD = "S3cure-Passw0rd!x"


class RegistrationTests(TestCase):
    def test_registrationReturnsOneNormalizedUserWhenEmailHasMixedCaseAndSpaces(self):
        self.client.post(
            "/register/",
            {
                "email": "  Marek@Example.com  ",
                "password1": PASSWORD,
                "password2": PASSWORD,
            },
        )

        self.assertEqual(User.objects.count(), 1)
        registered_user = User.objects.get()
        self.assertEqual(registered_user.username, "marek@example.com")
        self.assertEqual(registered_user.email, "marek@example.com")

    def test_registrationReturnsRedirectToHomeWhenRegistrationSucceeds(self):
        response = self.client.post(
            "/register/",
            {
                "email": "marek@example.com",
                "password1": PASSWORD,
                "password2": PASSWORD,
            },
        )

        self.assertRedirects(response, "/")

    def test_registrationReturnsRedirectToNextWhenNextIsProvided(self):
        response = self.client.post(
            "/register/?next=/",
            {
                "email": "marek@example.com",
                "password1": PASSWORD,
                "password2": PASSWORD,
                "next": "/",
            },
        )

        self.assertRedirects(response, "/")

    def test_registrationReturnsFormErrorWhenEmailAlreadyRegistered(self):
        User.objects.create_user(
            username="marek@example.com",
            email="marek@example.com",
            password=PASSWORD,
        )

        response = self.client.post(
            "/register/",
            {
                "email": "MAREK@example.com",
                "password1": PASSWORD,
                "password2": PASSWORD,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("email", response.context["form"].errors)
        self.assertEqual(User.objects.count(), 1)

    def test_registrationPageReturnsOkWhenVisitorIsAnonymous(self):
        response = self.client.get("/register/")

        self.assertEqual(response.status_code, 200)


class LoginTests(TestCase):
    def setUp(self):
        self.registered_user = User.objects.create_user(
            username="marek@example.com",
            email="marek@example.com",
            password=PASSWORD,
        )

    def test_loginReturnsRedirectToHomeWhenEmailAndPasswordAreValid(self):
        response = self.client.post(
            "/login/",
            {"username": "  Marek@Example.com  ", "password": PASSWORD},
        )

        self.assertRedirects(response, "/")
        home_response = self.client.get("/")
        self.assertEqual(home_response.status_code, 200)
        self.assertContains(home_response, "marek@example.com")

    def test_loginReturnsFormErrorWhenPasswordIsInvalid(self):
        response = self.client.post(
            "/login/",
            {"username": "marek@example.com", "password": "Wrong-Passw0rd!x"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)


class AccessControlTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user(
            username="alice@example.com",
            email="alice@example.com",
            password=PASSWORD,
        )
        self.bob = User.objects.create_user(
            username="bob@example.com",
            email="bob@example.com",
            password=PASSWORD,
        )

    def test_homeReturnsLoginRedirectWhenVisitorIsAnonymous(self):
        response = self.client.get("/")

        self.assertRedirects(response, "/login/?next=/")

    def test_homeReturnsOnlyTheActingUserWhenTwoUsersLoginSeparately(self):
        self.client.login(username="alice@example.com", password=PASSWORD)
        alice_response = self.client.get("/")
        self.assertEqual(alice_response.wsgi_request.user, self.alice)

        self.client.logout()
        self.client.login(username="bob@example.com", password=PASSWORD)
        bob_response = self.client.get("/")
        self.assertEqual(bob_response.wsgi_request.user, self.bob)


class LogoutTests(TestCase):
    def setUp(self):
        self.logged_in_user = User.objects.create_user(
            username="marek@example.com",
            email="marek@example.com",
            password=PASSWORD,
        )
        self.client.login(username="marek@example.com", password=PASSWORD)

    def test_logoutReturnsMethodNotAllowedWhenRequestedWithGet(self):
        response = self.client.get("/logout/")

        self.assertEqual(response.status_code, 405)

    def test_logoutReturnsLoginRedirectAndClearsSessionWhenPostedAuthenticated(self):
        response = self.client.post("/logout/")

        self.assertRedirects(response, "/login/")
        self.assertFalse(response.wsgi_request.user.is_authenticated)
        self.assertNotIn("_auth_user_id", self.client.session)
