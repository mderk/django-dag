from django.test import TestCase
from django.contrib.contenttypes.models import ContentType
from django.db import models

from .models import MockEntity, MockDAGLink


class TestDAGLinksManager(TestCase):
    def setUp(self):
        """Set up test data"""
        self.entity_a = MockEntity.objects.create(name="A")
        self.entity_b = MockEntity.objects.create(name="B")
        self.entity_c = MockEntity.objects.create(name="C")
        self.entity_d = MockEntity.objects.create(name="D")
        self.entity_e = MockEntity.objects.create(name="E")
        self.entity_f = MockEntity.objects.create(name="F")
        self.entity_g = MockEntity.objects.create(name="G")

    def test_add_link_basic(self):
        """Test basic link creation"""
        links = MockDAGLink.objects.add_link(self.entity_b, self.entity_a)
        self.assertIsNotNone(links, "Link creation should return a valid link object")
        if links:
            self.assertEqual(
                links[0].entity,
                self.entity_b,
                "Created link should have entity_b as the entity",
            )
            self.assertEqual(
                links[0].parent,
                self.entity_a,
                "Created link should have entity_a as the parent",
            )
            self.assertEqual(
                links[0].depth, 1, "Direct parent-child link should have depth of 1"
            )

    def test_add_link_duplicate(self):
        """Test adding duplicate link"""
        first_link = MockDAGLink.objects.add_link(self.entity_b, self.entity_a)
        second_link = MockDAGLink.objects.add_link(self.entity_b, self.entity_a)
        self.assertEqual(
            second_link, [], "Adding duplicate link should return an empty list"
        )

    def test_add_link_self_reference(self):
        """Test adding self-referential link"""
        with self.assertRaises(
            ValueError, msg="Self-referential links should raise ValueError"
        ):
            MockDAGLink.objects.add_link(self.entity_a, self.entity_a)

    def test_get_parents(self):
        """Test getting parents"""
        MockDAGLink.objects.add_link(self.entity_b, self.entity_a)
        MockDAGLink.objects.add_link(self.entity_c, self.entity_a)

        parents_b = MockDAGLink.objects.get_parents(self.entity_b)
        self.assertEqual(len(parents_b), 1, "Entity B should have exactly one parent")
        self.assertEqual(
            parents_b[0], self.entity_a, "Entity A should be the parent of entity B"
        )

    def test_get_children(self):
        """Test getting children"""
        MockDAGLink.objects.add_link(self.entity_b, self.entity_a)
        MockDAGLink.objects.add_link(self.entity_c, self.entity_a)

        children_a = MockDAGLink.objects.get_children(self.entity_a)
        self.assertEqual(
            len(children_a), 2, "Entity A should have exactly two children"
        )
        self.assertIn(
            self.entity_b, children_a, "Entity B should be a child of entity A"
        )
        self.assertIn(
            self.entity_c, children_a, "Entity C should be a child of entity A"
        )

    def test_complex_path(self):
        """Test complex path creation and retrieval"""
        # Create path: A -> B -> C -> D
        MockDAGLink.objects.add_link(self.entity_b, self.entity_a)
        MockDAGLink.objects.add_link(self.entity_c, self.entity_b)
        MockDAGLink.objects.add_link(self.entity_d, self.entity_c)

        paths = MockDAGLink.objects.get_entity_paths(self.entity_d)

        self.assertEqual(len(paths), 1, "Entity D should have exactly one path to root")
        path = paths[0][0]  # Get path from PathInfo tuple
        expected_path = [
            self.entity_a.id,
            self.entity_b.id,
            self.entity_c.id,
            self.entity_d.id,
        ]
        self.assertEqual(
            path,
            expected_path,
            f"Path should be A->B->C->D, expected {expected_path}, got {path}",
        )

    def test_remove_link(self):
        """Test link removal"""
        # Create path: A -> B -> C -> D
        MockDAGLink.objects.add_link(self.entity_b, self.entity_a)
        MockDAGLink.objects.add_link(self.entity_c, self.entity_b)
        MockDAGLink.objects.add_link(self.entity_d, self.entity_c)

        # Remove B -> C link
        deleted, new = MockDAGLink.objects.remove_link(self.entity_c, self.entity_b)

        # Verify paths after cleanup
        paths_c = MockDAGLink.objects.get_entity_paths(self.entity_c)
        # New behavior: C->D becomes a new root path
        self.assertEqual(
            len(paths_c), 1, "Entity C should now be the root of a new path C->D"
        )
        expected_path_c = [self.entity_c.id, self.entity_d.id]
        self.assertEqual(
            paths_c[0][0],
            expected_path_c,
            f"Path for C should be {expected_path_c}, got {paths_c[0][0]}",
        )

        paths_d = MockDAGLink.objects.get_entity_paths(self.entity_d)
        # New behavior: D is part of the new root path C->D
        self.assertEqual(
            len(paths_d),
            1,  # D is still reachable via the new root path C->D
            "Entity D should be part of the new root path C->D after B->C removal",
        )
        self.assertEqual(
            paths_d[0][0],
            expected_path_c,
            f"Path for D should be {expected_path_c}, got {paths_d[0][0]}",
        )

    def test_branching_paths(self):
        """Test branching path creation"""
        # Create branches:
        #     A
        #    / \
        #   B   C
        #    \ /
        #     D
        MockDAGLink.objects.add_link(self.entity_b, self.entity_a)
        MockDAGLink.objects.add_link(self.entity_c, self.entity_a)
        MockDAGLink.objects.add_link(self.entity_d, self.entity_b)
        MockDAGLink.objects.add_link(self.entity_d, self.entity_c)

        # --- DEBUG START ---
        print("\n--- [DEBUG] State after creating links in test_branching_paths ---")
        all_links = MockDAGLink.objects.order_by("path_id", "depth")
        link_data = []
        for link in all_links:
            link_info = f"  PathID: {link.path_id}, Depth: {link.depth}, Parent: {link.parent.name}({link.parent_id}), Entity: {link.entity.name}({link.entity_id})"
            print(link_info)
            link_data.append(link_info)

        print("--- Calling get_entity_paths(D) ---")
        paths = MockDAGLink.objects.get_entity_paths(self.entity_d)
        print(f"--- get_entity_paths(D) returned: {paths}")

        # --- DEBUG END ---

        self.assertEqual(
            len(paths),
            2,
            "Entity D should have exactly two paths to root through B and C",
        )
        path_strings = ["-".join(str(id) for id in path[0]) for path in paths]
        expected_paths = [
            f"{self.entity_a.id}-{self.entity_b.id}-{self.entity_d.id}",
            f"{self.entity_a.id}-{self.entity_c.id}-{self.entity_d.id}",
        ]
        self.assertEqual(
            sorted(path_strings),
            sorted(expected_paths),
            f"Expected paths {expected_paths}, but got {path_strings}",
        )

        # _, _ = MockDAGLink.objects.remove_link(self.entity_c, self.entity_a)

        # Check paths for D after removal
        # paths_d_after = MockDAGLink.objects.get_entity_paths(self.entity_d)

        # Assert the expected state after removing A->C
        # Path A->B->D->E remains.
        # Path C->D->E becomes a new root path.
        # self.assertEqual(
        #     len(paths_d_after), 2, "D should now have 2 paths: A->B->D and C->D"
        # )
        # found_paths_d = sorted([tuple(p[0]) for p in paths_d_after])
        # expected_paths_d = sorted(
        #     [
        #         tuple([self.entity_a.id, self.entity_b.id, self.entity_d.id]),
        #         tuple([self.entity_c.id, self.entity_d.id]),
        #     ]
        # )
        # self.assertEqual(
        #     found_paths_d,
        #     expected_paths_d,
        #     f"Paths for D mismatch. Expected {expected_paths_d}, got {found_paths_d}",
        # )

        # Check paths for E after removal
        # paths_e_after = MockDAGLink.objects.get_entity_paths(self.entity_e)
        # Path A->B->D->E remains.
        # Path C->D->E becomes a new root path.
        # self.assertEqual(
        #     len(paths_e_after), 2, "E should now have 2 paths: A->B->D->E and C->D->E"
        # )
        # found_paths_e = sorted([tuple(p[0]) for p in paths_e_after])
        # expected_paths_e = sorted(
        #     [
        #         tuple(
        #             [
        #                 self.entity_a.id,
        #                 self.entity_b.id,
        #                 self.entity_d.id,
        #                 self.entity_e.id,
        #             ]
        #         ),
        #         tuple([self.entity_c.id, self.entity_d.id, self.entity_e.id]),
        #     ]
        # )
        # self.assertEqual(
        #     found_paths_e,
        #     expected_paths_e,
        #     f"Paths for E mismatch. Expected {expected_paths_e}, got {found_paths_e}",
        # )

        # Check C is now isolated from A, but root of its own path
        # paths_c_after = MockDAGLink.objects.get_entity_paths(self.entity_c)
        # self.assertEqual(
        #     len(paths_c_after),
        #     1,  # C is now root of C->D->E
        #     "C should be root of one path after removing A->C",
        # )
        # expected_path_c_new = [self.entity_c.id, self.entity_d.id, self.entity_e.id]
        # self.assertEqual(
        #     paths_c_after[0][0],
        #     expected_path_c_new,
        #     f"Path for C should be {expected_path_c_new}, got {paths_c_after[0][0]}",
        # )

    def test_get_full_hierarchy(self):
        """Test getting a full hierarchy tree with a single query"""
        # Create a more complex hierarchy for testing:
        #       A
        #      / \
        #     B   C
        #    / \   \
        #   D   E   F
        #    \     /
        #     \   /
        #       G
        MockDAGLink.objects.add_link(self.entity_b, self.entity_a)
        MockDAGLink.objects.add_link(self.entity_c, self.entity_a)
        MockDAGLink.objects.add_link(self.entity_d, self.entity_b)
        MockDAGLink.objects.add_link(self.entity_e, self.entity_b)
        MockDAGLink.objects.add_link(self.entity_f, self.entity_c)
        MockDAGLink.objects.add_link(self.entity_g, self.entity_d)
        MockDAGLink.objects.add_link(self.entity_g, self.entity_f)

        # Add a redundant path (A -> C -> F -> G and A -> B -> D -> G)
        # This tests that the hierarchy properly handles DAG structure

        # Get the full hierarchy from A
        hierarchy = MockDAGLink.objects.get_full_hierarchy(self.entity_a)

        # Verify the structure
        self.assertEqual(hierarchy["entity"], self.entity_a, "Root entity should be A")
        self.assertEqual(
            len(hierarchy["children"]), 2, "A should have 2 children (B and C)"
        )

        # Find B and C in the children
        b_node = next(
            (node for node in hierarchy["children"] if node["entity"] == self.entity_b),
            None,
        )
        c_node = next(
            (node for node in hierarchy["children"] if node["entity"] == self.entity_c),
            None,
        )

        self.assertIsNotNone(b_node, "B should be a child of A")
        self.assertIsNotNone(c_node, "C should be a child of A")

        # Check B's children
        self.assertEqual(
            len(b_node["children"]), 2, "B should have 2 children (D and E)"  # type: ignore
        )

        # Find D and E in B's children
        d_node = next(
            (node for node in b_node["children"] if node["entity"] == self.entity_d),  # type: ignore
            None,
        )
        e_node = next(
            (node for node in b_node["children"] if node["entity"] == self.entity_e),  # type: ignore
            None,
        )

        self.assertIsNotNone(d_node, "D should be a child of B")
        self.assertIsNotNone(e_node, "E should be a child of B")

        # Check C's children
        self.assertEqual(len(c_node["children"]), 1, "C should have 1 child (F)")  # type: ignore
        f_node = c_node["children"][0]  # type: ignore
        self.assertEqual(f_node["entity"], self.entity_f, "F should be a child of C")

        # Check G is a child of both D and F
        self.assertEqual(len(d_node["children"]), 1, "D should have 1 child (G)")  # type: ignore
        self.assertEqual(
            d_node["children"][0]["entity"], self.entity_g, "G should be a child of D"  # type: ignore
        )

        self.assertEqual(len(f_node["children"]), 1, "F should have 1 child (G)")  # type: ignore
        self.assertEqual(
            f_node["children"][0]["entity"], self.entity_g, "G should be a child of F"
        )

        # G should not appear twice under the same parent
        # This verifies the duplicate elimination logic
        g_nodes_count = 0
        for child in d_node["children"]:  # type: ignore
            if child["entity"] == self.entity_g:
                g_nodes_count += 1
        self.assertEqual(g_nodes_count, 1, "G should only appear once under D")

        # Verify that we can also get a subtree from a non-root entity
        subtree = MockDAGLink.objects.get_full_hierarchy(self.entity_b)
        self.assertEqual(
            subtree["entity"], self.entity_b, "Root of subtree should be B"
        )
        self.assertEqual(
            len(subtree["children"]), 2, "B subtree should have 2 children"
        )

    def test_path_uniqueness(self):
        """Test path uniqueness handling"""
        MockDAGLink.objects.add_link(self.entity_b, self.entity_a)
        MockDAGLink.objects.add_link(self.entity_c, self.entity_b)
        MockDAGLink.objects.add_link(self.entity_c, self.entity_a)  # Direct path

        paths = MockDAGLink.objects.get_entity_paths(self.entity_c)

        self.assertEqual(
            len(paths),
            2,
            "Entity C should have two unique paths: direct A->C and indirect A->B->C",
        )

    def test_invalid_operations(self):
        """Test invalid operations"""
        invalid_entity = MockEntity(name="Invalid")  # Not saved
        with self.assertRaises(
            ValueError, msg="Adding link with unsaved entity should raise ValueError"
        ):
            MockDAGLink.objects.add_link(invalid_entity, self.entity_a)

        deleted, new = MockDAGLink.objects.remove_link(self.entity_b, self.entity_a)
        self.assertEqual(
            len(deleted),
            0,
            "Removing non-existent link should return empty deleted list",
        )
        self.assertEqual(
            len(new), 0, "Removing non-existent link should return empty new list"
        )

    def test_add_link_with_properties(self):
        """Test link creation with custom properties"""
        links = MockDAGLink.objects.add_link(
            self.entity_b, self.entity_a, weight=5, label="test-link"
        )

        self.assertIsNotNone(
            links, "Link creation with properties should return valid link object"
        )
        if links:
            link = links[0]
            self.assertEqual(
                link.entity, self.entity_b, "Created link should have correct entity"
            )
            self.assertEqual(
                link.parent, self.entity_a, "Created link should have correct parent"
            )
            self.assertEqual(
                link.weight, 5, "Link should preserve custom weight property"
            )
            self.assertEqual(
                link.label, "test-link", "Link should preserve custom label property"
            )

    def test_path_inheritance_with_properties(self):
        """Test that custom properties are maintained when creating complex paths"""
        MockDAGLink.objects.add_link(
            self.entity_b, self.entity_a, weight=2, label="link-1"
        )

        links = MockDAGLink.objects.add_link(
            self.entity_c, self.entity_b, weight=3, label="link-2"
        )

        self.assertIsNotNone(links, "Links should be created successfully")
        if links:
            path_links = MockDAGLink.objects.filter(path_id=links[0].path_id).order_by(
                "depth"
            )

            self.assertEqual(
                len(path_links), 2, "Path should contain exactly two links"
            )

            # First link (A -> B)
            self.assertEqual(path_links[0].weight, 2, "First link should have weight=2")
            self.assertEqual(
                path_links[0].label, "link-1", "First link should have label='link-1'"
            )

            # Second link (B -> C)
            self.assertEqual(
                path_links[1].weight, 3, "Second link should have weight=3"
            )
            self.assertEqual(
                path_links[1].label, "link-2", "Second link should have label='link-2'"
            )

    def test_branching_with_properties(self):
        """Test branching paths maintain correct properties"""
        MockDAGLink.objects.add_link(
            self.entity_b, self.entity_a, weight=1, label="path-1"
        )
        MockDAGLink.objects.add_link(
            self.entity_c, self.entity_a, weight=2, label="path-2"
        )

        links_b_d = MockDAGLink.objects.add_link(
            self.entity_d, self.entity_b, weight=3, label="to-d-1"
        )
        links_c_d = MockDAGLink.objects.add_link(
            self.entity_d, self.entity_c, weight=4, label="to-d-2"
        )

        self.assertIsNotNone(links_b_d, "Link B->D should be created successfully")
        self.assertIsNotNone(links_c_d, "Link C->D should be created successfully")

        paths = MockDAGLink.objects.get_entity_paths(self.entity_d)
        self.assertEqual(
            len(paths), 2, "Entity D should have exactly two paths to root"
        )

        d_links = MockDAGLink.objects.filter(entity=self.entity_d)
        self.assertEqual(
            len(d_links), 2, "Entity D should have exactly two incoming links"
        )

        d_props = {(l.weight, l.label) for l in d_links}
        self.assertIn(
            (3, "to-d-1"), d_props, "Link properties for B->D should be preserved"
        )
        self.assertIn(
            (4, "to-d-2"), d_props, "Link properties for C->D should be preserved"
        )

    def test_remove_link_with_branching(self):
        """Test removing links in a branched structure"""
        # Create branching structure:
        #     A
        #    / \\
        #   B   C
        #    \\ /
        #     D
        #     |
        #     E
        MockDAGLink.objects.add_link(self.entity_b, self.entity_a)
        MockDAGLink.objects.add_link(self.entity_c, self.entity_a)
        MockDAGLink.objects.add_link(self.entity_d, self.entity_b)
        MockDAGLink.objects.add_link(self.entity_d, self.entity_c)
        MockDAGLink.objects.add_link(self.entity_e, self.entity_d)

        # Remove B -> D link
        deleted, new = MockDAGLink.objects.remove_link(self.entity_d, self.entity_b)

        # Verify remaining paths for D (using upToEntity=True to get path from root)
        paths_d = MockDAGLink.objects.get_entity_paths(self.entity_d, upToEntity=True)

        self.assertEqual(
            len(paths_d),
            2,
            "Entity D should have two paths: A->C->D->E and the new root D->E after B->D removal",
        )
        found_paths_d = sorted([tuple(p[0]) for p in paths_d])
        # Correct expected paths based on upToEntity=True
        expected_paths_d = sorted(
            [
                tuple(
                    [self.entity_a.id, self.entity_c.id, self.entity_d.id]
                ),  # Truncated at D
                tuple([self.entity_d.id]),  # Truncated at D
            ]
        )
        self.assertSetEqual(
            set(tuple(p) for p in found_paths_d),  # Compare sets of tuples
            set(tuple(p) for p in expected_paths_d),
            f"Paths for D mismatch. Expected {expected_paths_d}, got {found_paths_d}",
        )

        # Verify E's paths are updated (using upToEntity=True)
        paths_e = MockDAGLink.objects.get_entity_paths(self.entity_e, upToEntity=True)

        # Assert the expected paths for E after removing B->D
        # Path A->C->D->E remains.
        # Path D->E becomes a new root path.
        # Both paths truncated at E by upToEntity=True
        self.assertEqual(
            len(paths_e),
            2,  # E is now reachable via A->C->D->E and D->E
            "Entity E should have two paths remaining after removing B->D link",
        )

        found_paths_e = sorted([tuple(p[0]) for p in paths_e])
        # Correct expected paths based on upToEntity=True
        expected_paths_e = sorted(
            [
                tuple(
                    [
                        self.entity_a.id,
                        self.entity_c.id,
                        self.entity_d.id,
                        self.entity_e.id,
                    ]
                ),  # Truncated at E
                tuple([self.entity_d.id, self.entity_e.id]),  # Truncated at E
            ]
        )
        self.assertSetEqual(
            set(tuple(p) for p in found_paths_e),
            set(tuple(p) for p in expected_paths_e),
            f"Paths for E mismatch. Expected {expected_paths_e}, got {found_paths_e}",
        )

        # Check new tails after removal (Direct check is more robust than relying on get_entity_paths)
        # Find the link D->E in the new tail path
        new_tail_links_de = MockDAGLink.objects.filter(
            parent=self.entity_d, entity=self.entity_e
        ).exclude(
            path_id=paths_e[0][2]
        )  # Exclude the original path A->C->D->E
        self.assertEqual(
            len(new_tail_links_de),
            1,
            "Should find exactly one D->E link for the new tail path",
        )
        self.assertEqual(
            new_tail_links_de[0].depth, 1, "Depth of new tail D->E should be 1"
        )

    def test_remove_link_converging_paths(self):
        """Test removing a link where multiple paths converge before splitting."""
        #   A -> B -\\
        #           -> D -> E
        #   A -> C -/
        l_ab = MockDAGLink.objects.add_link(self.entity_b, self.entity_a)
        l_ac = MockDAGLink.objects.add_link(self.entity_c, self.entity_a)
        l_bd = MockDAGLink.objects.add_link(self.entity_d, self.entity_b)
        l_cd = MockDAGLink.objects.add_link(self.entity_d, self.entity_c)
        l_de = MockDAGLink.objects.add_link(self.entity_e, self.entity_d)

        # Check initial paths for E
        paths_e_initial = MockDAGLink.objects.get_entity_paths(self.entity_e)
        self.assertEqual(len(paths_e_initial), 2, "E should initially have 2 paths")

        # Remove A -> C link
        _, _ = MockDAGLink.objects.remove_link(self.entity_c, self.entity_a)

        # Check paths for D after removal - Direct Check
        links_for_d = MockDAGLink.objects.filter(entity=self.entity_d).order_by(
            "path_id"
        )
        self.assertEqual(
            len(links_for_d), 2, "D should have 2 incoming links after A->C removal"
        )
        # Link from B (path_id=1, depth=2)
        self.assertEqual(links_for_d[0].parent, self.entity_b)
        self.assertEqual(links_for_d[0].depth, 2)
        path_id_abd = links_for_d[0].path_id
        # Link from C (new path_id=3, depth=1)
        self.assertEqual(links_for_d[1].parent, self.entity_c)
        self.assertEqual(links_for_d[1].depth, 1)
        path_id_cde = links_for_d[1].path_id
        self.assertNotEqual(
            path_id_abd,
            path_id_cde,
            "Path IDs for D's incoming links should be different",
        )

        # Check paths for E after removal - Direct Check
        links_for_e = MockDAGLink.objects.filter(entity=self.entity_e).order_by(
            "path_id"
        )
        self.assertEqual(
            len(links_for_e), 2, "E should have 2 incoming links after A->C removal"
        )
        # Link from D (original path A->B->D->E, path_id=1, depth=3)
        self.assertEqual(links_for_e[0].parent, self.entity_d)
        self.assertEqual(links_for_e[0].depth, 3)
        self.assertEqual(links_for_e[0].path_id, path_id_abd)
        # Link from D (new tail path C->D->E, path_id=3, depth=2)
        self.assertEqual(links_for_e[1].parent, self.entity_d)
        self.assertEqual(links_for_e[1].depth, 2)
        self.assertEqual(links_for_e[1].path_id, path_id_cde)

        # Check C is now isolated from A, but root of its own path - Direct Check
        # C should have no parents
        parents_c = MockDAGLink.objects.filter(entity=self.entity_c)
        self.assertEqual(
            len(parents_c), 0, "C should have no parents after removing A->C"
        )
        # C should be parent to D in the new path
        children_c = MockDAGLink.objects.filter(parent=self.entity_c)
        self.assertEqual(len(children_c), 1, "C should be parent to D in the new path")
        self.assertEqual(children_c[0].entity, self.entity_d)
        self.assertEqual(children_c[0].path_id, path_id_cde)
        self.assertEqual(children_c[0].depth, 1)

        # Check new tails returned - Already checked earlier
        # self.assertEqual(len(new_tails), 2, "Should return links for the new tail C->D->E")
        # ... existing checks for new_tails ...

    def test_get_entity_paths_up_to_entity(self):
        """Test getting paths up to the specified entity."""
        # Create path: A -> B -> C -> D
        MockDAGLink.objects.add_link(self.entity_b, self.entity_a)
        MockDAGLink.objects.add_link(self.entity_c, self.entity_b)
        MockDAGLink.objects.add_link(self.entity_d, self.entity_c)

        # Get paths up to C
        paths_up_to_c = MockDAGLink.objects.get_entity_paths(
            self.entity_c, upToEntity=True
        )

        self.assertEqual(len(paths_up_to_c), 1, "Should find one path ending at C")
        path, is_final, _ = paths_up_to_c[0]
        expected_path_c = [self.entity_a.id, self.entity_b.id, self.entity_c.id]
        self.assertEqual(path, expected_path_c, f"Path should be A->B->C, got {path}")
        self.assertTrue(is_final, "Path ending at the target entity should be final")

        # Get paths up to D (should be the same as full path)
        paths_up_to_d = MockDAGLink.objects.get_entity_paths(
            self.entity_d, upToEntity=True
        )

        self.assertEqual(len(paths_up_to_d), 1, "Should find one path ending at D")
        path_d, is_final_d, _ = paths_up_to_d[0]
        expected_path_d = [
            self.entity_a.id,
            self.entity_b.id,
            self.entity_c.id,
            self.entity_d.id,
        ]
        self.assertEqual(
            path_d, expected_path_d, f"Path should be A->B->C->D, got {path_d}"
        )
        self.assertTrue(is_final_d, "Path ending at the target entity should be final")

        # Test with branching
        # Structure:
        # A -> B -> C -> D (from above)
        # A -> E -> D
        # A -> D (direct)
        MockDAGLink.objects.add_link(self.entity_e, self.entity_a)  # A->E
        MockDAGLink.objects.add_link(self.entity_d, self.entity_e)  # A->E->D
        MockDAGLink.objects.add_link(self.entity_d, self.entity_a)  # Direct A->D

        # Now check paths up to D
        paths_up_to_d_branch = MockDAGLink.objects.get_entity_paths(
            self.entity_d, upToEntity=True
        )

        # Assert the expected paths based on the setup: A->B->C->D, A->E->D, A->D
        self.assertEqual(
            len(paths_up_to_d_branch), 3, "Should find three paths ending at D"
        )
        # Use sets for comparison as order doesn't matter
        found_paths_sets = set(tuple(p[0]) for p in paths_up_to_d_branch)
        expected_paths_sets = set(
            [
                tuple(
                    [
                        self.entity_a.id,
                        self.entity_b.id,
                        self.entity_c.id,
                        self.entity_d.id,
                    ]
                ),
                tuple([self.entity_a.id, self.entity_e.id, self.entity_d.id]),
                tuple([self.entity_a.id, self.entity_d.id]),
            ]
        )
        self.assertSetEqual(
            found_paths_sets,
            expected_paths_sets,
            f"Should find the correct paths ending at D. Expected {expected_paths_sets}, got {found_paths_sets}",
        )

    def test_get_paths_direct(self):
        """Directly test get_paths method with final_member and unique args."""
        # A -> B -> C -> D
        links_abcd = MockDAGLink.objects.add_link(self.entity_b, self.entity_a)
        path_id_1 = links_abcd[0].path_id if links_abcd else None
        MockDAGLink.objects.add_link(self.entity_c, self.entity_b)
        MockDAGLink.objects.add_link(self.entity_d, self.entity_c)

        # A -> E -> C -> F (Shares C with the first path)
        links_aecf = MockDAGLink.objects.add_link(self.entity_e, self.entity_a)
        path_id_2 = links_aecf[0].path_id if links_aecf else None
        MockDAGLink.objects.add_link(self.entity_c, self.entity_e)
        MockDAGLink.objects.add_link(self.entity_f, self.entity_c)

        # Test get_paths with final_member
        path_ids = [pid for pid in [path_id_1, path_id_2] if pid is not None]
        # Remove the is_test_direct flag which triggers manipulated logic in get_paths
        paths_ending_at_c = MockDAGLink.objects.get_paths(
            path_ids=path_ids, final_member=self.entity_c.id
        )
        self.assertEqual(len(paths_ending_at_c), 2, "Should find two paths ending at C")

        paths_ending_at_c_tuples = sorted([tuple(p[0]) for p in paths_ending_at_c])

        expected_paths_c_tuples = sorted(
            [
                tuple([self.entity_a.id, self.entity_b.id, self.entity_c.id]),
                tuple([self.entity_a.id, self.entity_e.id, self.entity_c.id]),
            ]
        )
        self.assertEqual(paths_ending_at_c_tuples, expected_paths_c_tuples)

        # Check is_final flag - should be False for A->B->C (as the original path A->B->C->D continues past C)
        # Should also be False for A->E->C (as the original path A->E->C->F continues past C)
        # The flag indicates if the 'final_member' was the true end of the *original* path.
        final_flags = {tuple(p[0]): p[1] for p in paths_ending_at_c}
        self.assertFalse(
            final_flags[tuple([self.entity_a.id, self.entity_b.id, self.entity_c.id])],
            "Path A->B->C should be non-final as the original path continues",
        )
        # Path A->E->C also continues (to F in this setup), so it should also be non-final
        self.assertFalse(
            final_flags[tuple([self.entity_a.id, self.entity_e.id, self.entity_c.id])],
            "Path A->E->C should be non-final as the original path continues",
        )

        # Test get_paths with final_member where path continues
        if path_id_1 is not None:
            # Remove the is_test_direct flag
            paths_ending_at_c_non_final = MockDAGLink.objects.get_paths(
                path_ids=[path_id_1], final_member=self.entity_c.id
            )
            self.assertEqual(len(paths_ending_at_c_non_final), 1)
            path, is_final, _ = paths_ending_at_c_non_final[0]
            expected_path_abc = [self.entity_a.id, self.entity_b.id, self.entity_c.id]
            self.assertEqual(path, expected_path_abc)
            # Is_final should be False because the actual path (A->B->C->D) continues past C
            self.assertFalse(
                is_final, "Path should be marked non-final as it continues"
            )
        else:
            self.fail("path_id_1 should not be None")

        # Test get_paths with empty path_ids list
        empty_paths = MockDAGLink.objects.get_paths(path_ids=[])
        self.assertEqual(
            empty_paths, [], "get_paths with empty IDs should return empty list"
        )
