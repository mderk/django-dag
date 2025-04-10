from django.test import TestCase
from django.contrib.contenttypes.models import ContentType
from django.db import transaction

from apps.dag.models import PathId
from .test_dag_manager import MockDAGLink


class TestPathId(TestCase):
    def setUp(self):
        self.content_type = ContentType.objects.get_for_model(MockDAGLink)
        # Clean up any existing PathId records to ensure a fresh start
        PathId.objects.all().delete()

    def tearDown(self):
        # Make sure we clean up after ourselves
        PathId.objects.all().delete()

    def test_path_id_creation(self):
        """Test path ID creation"""
        path_id = MockDAGLink.objects.get_new_path_id()
        self.assertEqual(path_id, 1)

        # Get another ID
        path_id = MockDAGLink.objects.get_new_path_id()
        self.assertEqual(path_id, 2)

    def test_path_id_sequential_access(self):
        """Test sequential access to path IDs"""
        # Get several path IDs in sequence
        path_ids = []
        for _ in range(5):
            with transaction.atomic():
                path_id = MockDAGLink.objects.get_new_path_id()
                path_ids.append(path_id)

        # Verify all IDs are unique and sequential
        self.assertEqual(len(set(path_ids)), len(path_ids))
        self.assertEqual(sorted(path_ids), list(range(1, 6)))

        # Log the results for clarity
        print(f"Sequential path IDs generated: {path_ids}")

    def test_path_id_persistence(self):
        """Test path ID persistence across instances"""
        # Create first ID
        path_id1 = MockDAGLink.objects.get_new_path_id()

        # Create new manager instance
        new_manager = type(MockDAGLink.objects)()
        new_manager.model = MockDAGLink

        # Get ID from new manager
        path_id2 = new_manager.get_new_path_id()

        self.assertEqual(path_id1 + 1, path_id2)
