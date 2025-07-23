from django.test import TestCase
from django.urls import reverse

from .models import CodeSource, CodeList


class CodelistSearchViewTests(TestCase):
    """Tests for the codelist_search view."""

    def setUp(self):
        self.source = CodeSource.objects.create(
            name="Test Source",
            description="Test description",
            is_default=True,
        )
        self.codelist = CodeList.objects.create(
            codelist_name="Hypertension",
            project_title="Test Project",
            author="Tester",
            source=self.source,
        )

    def test_codelist_search_returns_created_codelist(self):
        """Ensure the created codelist appears in search results."""
        url = reverse("codelist_search")
        response = self.client.get(url, {"search": "Hyper"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.codelist.codelist_name)

