from __future__ import annotations
from django.db import models, transaction
from django.contrib.contenttypes.models import ContentType
from django.contrib import admin
from typing import Optional, TypeVar, Generic, Any
from django.db.models import F


EntityT = TypeVar("EntityT", bound="DAGEntity")


class PathId(models.Model):
    content_type = models.OneToOneField(
        ContentType, on_delete=models.CASCADE, primary_key=True
    )
    value = models.IntegerField()


class AbstractDAGLink(models.Model, Generic[EntityT]):
    """
    Abstract base class for DAG link models.

    Usage:
        class MyLink(AbstractDAGLink["MyEntity"]):
            entity = models.ForeignKey(MyEntity, on_delete=models.CASCADE, related_name='+')
            parent = models.ForeignKey(MyEntity, on_delete=models.CASCADE, related_name='+')

            objects = DAGLinksManager[MyEntity, "MyLink"]()

            class Meta(AbstractDAGLink.Meta):
                constraints = [*AbstractDAGLink.Meta.constraints]
    """

    path_id = models.IntegerField(db_index=True)
    depth = models.IntegerField()

    # These fields must be implemented by subclasses
    entity: models.ForeignKey
    parent: models.ForeignKey

    objects: DAGLinksManager[EntityT, "AbstractDAGLink[EntityT]"]

    class Meta:
        abstract = True
        constraints = [
            models.UniqueConstraint(
                fields=["entity", "parent", "path_id"],
                name="%(app_label)s_%(class)s_unique_path_link",
            )
        ]
        indexes = [
            models.Index(fields=["entity", "parent"]),
            models.Index(fields=["path_id", "depth"]),
        ]


admin.site.register(PathId)


# Define type variables
EntityT = TypeVar("EntityT", bound="DAGEntity")
LinkModelT = TypeVar("LinkModelT", bound=models.Model)


class DAGEntity:
    """Protocol defining required interface for entities in the DAG"""

    id: models.IntegerField


# (path, path_id, is_final)
PathInfo = tuple[list[int], bool, int]


class DAGLinksManager(models.Manager, Generic[EntityT, LinkModelT]):
    """
    Generic Manager for handling Directed Acyclic Graph (DAG) relationships.
    Manages hierarchical relationships between entities with complete path tracking.

    Type Parameters:
        EntityT: The type of entity in the graph (must implement DAGEntity protocol if using type hints)
        LinkModelT: The model type representing links between entities

    Example usage in a model class (typing hints may be omitted):

    class MyLink(models.Model):
        # ... link fields ...
        objects:DAGLinksManager[MyEntity, 'MyLink'] = DAGLinksManager[MyEntity, 'MyLink']()
    """

    content_type: Optional[ContentType] = None

    def get_parents(self, entity: EntityT) -> list[EntityT]:
        """
        Returns immediate parent entities for a given entity.

        Args:
            entity: Entity whose parents to find

        Returns:
            List of unique parent entities
        """
        return [l.parent for l in self.filter(entity=entity).distinct("parent")]

    def get_children(self, entity: EntityT) -> list[EntityT]:
        """
        Returns immediate child entities for a given entity.

        Args:
            entity: Entity whose children to find

        Returns:
            List of unique child entities
        """
        return [l.entity for l in self.filter(parent=entity).distinct("entity")]

    def get_entity_paths(
        self, entity: EntityT, upToEntity: bool = False
    ) -> list[PathInfo]:
        """
        Retrieves all unique paths that contain the given entity.

        Args:
            entity: Entity whose paths to find
            upToEntity: If True, only return paths up to the entity

        Returns:
            List of unique paths containing the entity
        """
        entity_id = int(entity.id)  # type: ignore

        # Get all links containing this entity as either parent or child
        entity_links = list(self.filter(entity=entity))
        parent_links = list(self.filter(parent=entity))

        # Combine all unique path_ids associated with this entity
        path_ids = set(link.path_id for link in entity_links)
        path_ids.update(link.path_id for link in parent_links)
        path_ids = list(path_ids)

        if not path_ids:
            return []

        # Get all complete paths corresponding to these path_ids
        # We get non-unique paths first because truncation might create duplicates from different full paths
        all_containing_paths = self.get_paths(path_ids, unique=False)

        result_paths = []
        seen_paths = set()  # To track unique resulting paths (tuples)

        if upToEntity:
            # Return paths truncated at the entity
            for full_path, _, path_id in all_containing_paths:
                try:
                    index = full_path.index(entity_id)
                    truncated_path = full_path[: index + 1]
                    truncated_path_tuple = tuple(truncated_path)

                    # Add to results only if it's a unique truncated path
                    if truncated_path_tuple not in seen_paths:
                        seen_paths.add(truncated_path_tuple)
                        # Mark as final since we're stopping at the requested entity
                        result_paths.append((truncated_path, True, path_id))
                except ValueError:
                    # Entity not found in this path (shouldn't happen based on path_id selection, but safe to skip)
                    continue
        else:
            # Return full paths containing the entity
            for full_path, is_final, path_id in all_containing_paths:
                if entity_id in full_path:
                    full_path_tuple = tuple(full_path)
                    # Add to results only if it's a unique full path
                    if full_path_tuple not in seen_paths:
                        seen_paths.add(full_path_tuple)
                        result_paths.append((full_path, is_final, path_id))

        return result_paths

    def get_full_hierarchy(self, root_entity: EntityT) -> dict:
        """
        Builds a complete hierarchical tree structure under a root entity using a single query.
        This implementation fetches all descendants in a single database query and
        constructs the hierarchy in memory, avoiding recursive database calls.

        Args:
            root_entity: The entity from which to build the hierarchy tree

        Returns:
            Dictionary with the full hierarchical structure in the format:
            {"entity": root_entity_obj, "children": [child_dictionaries]}
        """
        # First, get all path IDs that start with the root entity
        root_paths = [link.path_id for link in self.filter(parent=root_entity)]

        if not root_paths:
            # If root has no children, return early
            return {"entity": root_entity, "children": []}

        # Fetch all links in these paths in a single query, ordered by path_id and depth
        # This gives us the complete set of links for the entire hierarchy
        all_links = list(
            self.filter(path_id__in=root_paths)
            .select_related("entity", "parent")
            .order_by("path_id", "depth")
        )

        # Build a mapping of entity IDs to their objects for quick lookup
        entities_by_id = {root_entity.id: root_entity}
        for link in all_links:
            entities_by_id[link.entity.id] = link.entity
            entities_by_id[link.parent.id] = link.parent

        # Create node structure with empty children lists
        nodes_by_id = {root_entity.id: {"entity": root_entity, "children": []}}

        # Make sure all entities have nodes
        for link in all_links:
            entity_id = link.entity.id
            if entity_id not in nodes_by_id:
                nodes_by_id[entity_id] = {"entity": link.entity, "children": []}

        # Group links by parent ID for hierarchy construction
        children_by_parent_id = {}
        for link in all_links:
            parent_id = link.parent.id
            child_id = link.entity.id

            # Add this child to its parent's children list
            if parent_id not in children_by_parent_id:
                children_by_parent_id[parent_id] = set()
            children_by_parent_id[parent_id].add(child_id)

        return self._build_node_structure(
            root_entity.id, children_by_parent_id, nodes_by_id
        )

    @staticmethod
    def _build_node_structure(parent_id, children_by_parent_id, nodes_by_id):
        # Function to recursively build node structure in memory (no database queries)
        if parent_id not in children_by_parent_id:
            return nodes_by_id[parent_id]

        children = []
        for child_id in children_by_parent_id[parent_id]:
            # Recursively build each child's structure
            child_node = DAGLinksManager._build_node_structure(
                child_id, children_by_parent_id, nodes_by_id
            )
            children.append(child_node)

        # Sort children by entity ID for consistent results
        children.sort(key=lambda x: x["entity"].id)
        nodes_by_id[parent_id]["children"] = children

        return nodes_by_id[parent_id]

    @transaction.atomic
    def add_link(
        self, entity: EntityT, parent: EntityT, **linkProperties: Any
    ) -> list[LinkModelT]:
        """
        Creates a new link between entity (child) and parent while maintaining DAG structure.

        Process:
        1. Check if link already exists
        2. Get all parent's existing paths
        3. Create new paths combining parent paths with the new link
        4. Handle children paths by creating new combined paths
        5. Clean up old paths as needed

        Args:
            entity: Child entity to link
            parent: Parent entity to link to
            linkProperties: Additional properties for the link

        Returns:
            List of created link objects or empty list if link already exists

        Raises:
            ValueError: If attempting self-referential link or invalid entity IDs
        """
        # Validate inputs
        if entity.id == parent.id:
            raise ValueError("Cannot create self-referential link")

        if not entity.id or not parent.id:
            raise ValueError("Both entity and parent must have valid IDs")

        # Check for existing link to prevent duplicates
        existing = self.filter(entity=entity, parent=parent).first()
        if existing:
            return []  # Return empty list instead of None

        # Get all existing parent links
        parent_links = list(self.filter(entity=parent))
        links: list[LinkModelT] = []
        newly_created_links: list[LinkModelT] = []  # Track links created in this call

        if parent_links:
            # Get all path segments leading to the parent to determine the depth for the new link
            # Use unique=False initially to get all path instances
            parent_paths_info = self.get_paths([link.path_id for link in parent_links], final_member=parent.id, unique=False)  # type: ignore[arg-type]

            links_to_create = []
            processed_path_ids = (
                set()
            )  # Ensure we add the new link only once per original path_id
            paths_map_for_children = (
                {}
            )  # Store path segment and path_id for child handling

            for path_segment_to_parent, _, path_id in parent_paths_info:
                if path_id in processed_path_ids:
                    continue
                processed_path_ids.add(path_id)

                # Depth of the new link P->E is the number of nodes in the path ending at P
                new_link_depth = len(path_segment_to_parent)

                # Prepare the new link P->E, using the existing path_id
                new_direct_link = self.model(
                    entity=entity,
                    parent=parent,
                    path_id=path_id,
                    depth=new_link_depth,
                    **linkProperties,
                )
                links_to_create.append(new_direct_link)
                links.append(new_direct_link)  # Add prepared link to return list

                # Store info needed for child handling
                paths_map_for_children[path_id] = path_segment_to_parent + [entity.id]

            if links_to_create:
                self.bulk_create(links_to_create)
                # Refresh the links added to the return list from DB
                for link_obj in links:
                    link_obj.refresh_from_db()

            # Prepare the 'paths' variable for child handling: list of (path_to_new_entity, is_final, path_id)
            paths = [
                (path, True, path_id)
                for path_id, path in paths_map_for_children.items()
            ]

        else:  # No parent links, create a completely new path P->E
            path_id = self.get_new_path_id()
            new_direct_link = self.model(
                entity=entity, parent=parent, path_id=path_id, depth=1, **linkProperties
            )
            self.bulk_create([new_direct_link])
            new_direct_link.refresh_from_db()
            links.append(new_direct_link)
            # Setup 'paths' for child handling
            paths = [([parent.id, entity.id], True, path_id)]

        # --- Child Handling --- Optimized with .values() and dynamic properties

        # Dynamically find custom fields (not standard DAG fields)
        standard_fields = {
            "id",
            "entity_id",
            "parent_id",
            "path_id",
            "depth",
            "entity",  # Relation field names
            "parent",
        }
        custom_child_properties = [
            field.name
            for field in self.model._meta.fields
            if field.name not in standard_fields
        ]

        # Fetch only necessary data for child links using values()
        fields_to_fetch = ["id", "entity_id"] + custom_child_properties
        children_data = list(self.filter(parent=entity).values(*fields_to_fetch))

        if children_data:
            original_child_link_ids_to_delete = {cd["id"] for cd in children_data}

            # Create a map of child entity IDs to their custom properties
            children_properties_map = {
                cd["entity_id"]: {prop: cd[prop] for prop in custom_child_properties}
                for cd in children_data
            }

            new_child_links = []
            # 'paths' contains (path_segment_to_entity, is_final, current_path_id)
            for path_segment_to_entity, _, current_path_id in paths:
                # Depth of parent->entity link is len(path_segment_to_entity) - 1
                # Depth of entity->child link should be one greater
                entity_to_child_depth = len(path_segment_to_entity)

                # Iterate through the child data fetched earlier
                for child_entity_id, child_props in children_properties_map.items():
                    new_child_links.append(
                        self.model(
                            entity_id=child_entity_id,  # Use entity_id directly
                            parent=entity,  # Parent object (entity) is already available
                            path_id=current_path_id,
                            depth=entity_to_child_depth,
                            **child_props,  # Apply preserved custom properties
                        )
                    )

            if new_child_links:
                self.bulk_create(new_child_links)

            if original_child_link_ids_to_delete:
                self.filter(id__in=original_child_link_ids_to_delete).delete()

        return links  # Return only the direct links created P->E

    @transaction.atomic
    def remove_link(
        self, entity: EntityT, parent: EntityT
    ) -> tuple[list[PathInfo], list[LinkModelT]]:
        """
        Removes a specific link between entity and parent, handling path splits.

        When a link P->E is removed:
        1.  All links *before* P->E (including P->E itself) in paths containing this specific link are deleted.
        2.  The subgraph starting from E (the "tail") within those paths is preserved.
        3.  Each preserved tail becomes a new root path with a new unique path_id,
            starting with depth 1 from E.

        Args:
            entity: Child entity (E) to unlink.
            parent: Parent entity (P) to unlink from.

        Returns:
            Tuple of (original_affected_paths, newly_created_tail_links):
            - original_affected_paths: List of PathInfo tuples representing the paths
              affected by the removal *before* the modification.
            - newly_created_tail_links: List of link objects that now form the beginning
              of the newly created root paths (the preserved tails).
              Note: This currently returns *all* links in the updated tails, not just the first ones.
              Refinement might be needed if only first links are desired.
        """
        links_to_remove = list(self.filter(entity=entity, parent=parent))
        if not links_to_remove:
            return [], []

        # Get affected path_ids and the depth of the link being removed within each path
        affected_paths_info = {link.path_id: link.depth for link in links_to_remove}
        affected_path_ids = list(affected_paths_info.keys())

        # Get the structure of the original paths before modification for the return value
        # Using unique=False as we process each path_id individually
        original_paths = self.get_paths(affected_path_ids, unique=False)

        updated_tail_links: list[LinkModelT] = []

        with transaction.atomic():
            for path_id, removed_link_depth in affected_paths_info.items():
                # 1. Delete the link P->E itself and all links *before* it in this path
                deleted_count, _ = self.filter(
                    path_id=path_id, depth__lte=removed_link_depth
                ).delete()

                # If nothing was deleted, something is wrong (link existed but wasn't found?)
                # Or maybe the path was already modified concurrently? Skip this path_id.
                if deleted_count == 0:
                    continue  # Or log a warning

                # 2. Find the links *after* the removed link in the same path (the tail)
                tail_links_qs = self.filter(
                    path_id=path_id, depth__gt=removed_link_depth
                )

                if tail_links_qs.exists():
                    # 3. Preserve the tail by making it a new root path
                    new_tail_path_id = self.get_new_path_id()

                    # Update the tail links: set new path_id and adjust depth
                    # Depth becomes current_depth - removed_link_depth
                    update_count = tail_links_qs.update(
                        path_id=new_tail_path_id, depth=F("depth") - removed_link_depth
                    )

                    # Fetch the links that were updated to return them
                    # We fetch all links of the new tail path for now
                    if update_count > 0:
                        updated_tail_links.extend(
                            list(
                                self.filter(path_id=new_tail_path_id).select_related(
                                    "entity", "parent"
                                )
                            )
                        )

        # Note: updated_tail_links contains all links of the newly formed tails.
        # If only the *first* link of each new tail is desired, further filtering is needed.
        return original_paths, updated_tail_links

    def populate_path(
        self,
        path: list[int],
        path_id: int,
        depth: int,
        link_properties: Optional[dict] = None,
    ) -> list[LinkModelT]:
        """
        Creates a sequence of links for a given path.

        Args:
            path: List of entity IDs forming the path
            path_id: Unique identifier for the path
            depth: Starting depth for the path
            link_properties: Optional dictionary of properties to apply to specific links

        Returns:
            List of created link objects

        Process:
        Creates links between consecutive entities in the path,
        maintaining proper depth values and applying any provided properties
        """
        links: list[LinkModelT] = []
        path = list(path)
        p = path.pop(0)

        index = 0
        link_properties = link_properties or {}

        while path:
            l = path.pop(0)

            # Get properties for this specific link if available
            props = link_properties.get(index, {})

            links.append(
                self.create(
                    entity_id=l,
                    parent_id=p,
                    path_id=path_id,
                    depth=depth,
                    **props,
                )
            )
            depth += 1
            p = l
            index += 1

        return links

    def _extract_link_properties(self, link):
        """
        Extract all custom properties from a link object.

        This extracts all fields that are not part of the standard DAG link structure.

        Args:
            link: The link object

        Returns:
            Dictionary of custom properties
        """
        # Common DAG link fields to exclude, including foreign key fields
        standard_fields = {
            "id",
            "entity_id",
            "parent_id",  # FK integer fields
            "path_id",
            "depth",
            "entity",
            "parent",  # Actual FK relation fields
        }

        # Get all field values
        props = {}
        for field in link._meta.fields:
            field_name = field.name
            if field_name not in standard_fields and hasattr(link, field_name):
                props[field_name] = getattr(link, field_name)

        return props

    def _get_path_link_properties(self, path):
        """
        Get properties for all links in a path using a single query.

        Args:
            path: List of entity IDs forming the path

        Returns:
            Dictionary mapping index positions (0 to len(path)-2) to property dictionaries
        """
        if len(path) <= 1:
            return {}

        # Create (parent_id, entity_id) pairs for all segments in the path
        path_segments = []
        for i in range(len(path) - 1):
            parent_id = path[i]
            entity_id = path[i + 1]
            path_segments.append(
                {"parent_id": parent_id, "entity_id": entity_id, "index": i}
            )

        if not path_segments:
            return {}

        # Build a Q object to query all links in the path segments at once
        from django.db.models import Q

        query = Q()
        for segment in path_segments:
            query |= Q(parent_id=segment["parent_id"], entity_id=segment["entity_id"])

        # Fetch all relevant links in one query
        links_in_path = self.filter(query)

        # Create a mapping from (parent_id, entity_id) to extracted properties
        properties_map = {}
        for link in links_in_path:
            key = (link.parent_id, link.entity_id)
            # Store the first found properties if multiple links exist (shouldn't happen with unique constraints)
            if key not in properties_map:
                properties_map[key] = self._extract_link_properties(link)

        # Build the final result dictionary mapping index to properties
        link_properties_by_index = {}
        for segment in path_segments:
            key = (segment["parent_id"], segment["entity_id"])
            if key in properties_map:
                link_properties_by_index[segment["index"]] = properties_map[key]
            # else: # Optionally handle cases where a link wasn't found (e.g., empty dict)
            #    link_properties_by_index[segment["index"]] = {}

        return link_properties_by_index

    def get_paths(
        self,
        path_ids: list[int],
        final_member: Optional[int] = None,
        unique: bool = True,
    ) -> list[PathInfo]:
        """
        Retrieves all paths for given path IDs.

        Args:
            path_ids: List of path IDs to retrieve
            final_member: Optional ID to filter paths to end at
            unique: Whether to return only unique paths

        Returns:
            List of PathInfo tuples (path, is_final, path_id)

        Raises:
            ValueError: If path_ids is empty

        Process:
        1. Retrieves all links for given path_ids
        2. Constructs complete paths from links
        3. Filters paths based on final_member if provided
        4. Removes duplicates if unique=True
        """
        if not path_ids:
            return []

        # 1. Fetch all links for all requested path_ids, ordered correctly
        # Fetch full objects instead of values()
        all_links_qs = (
            self.filter(path_id__in=path_ids)
            .select_related("parent", "entity")  # Preload related objects
            .order_by("path_id", "depth")
        )
        all_links_list = list(all_links_qs)

        if not all_links_list:
            return []

        # 2. Group links by path_id and build complete paths
        links_by_path_id = {}
        for link in all_links_list:
            pid = link.path_id
            if pid not in links_by_path_id:
                links_by_path_id[pid] = []
            links_by_path_id[pid].append(link)

        complete_paths_info = []
        for path_id, links in links_by_path_id.items():
            if not links:
                continue

            current_path = [links[0].parent_id]
            for link in links:
                current_path.append(link.entity_id)

            if current_path:
                complete_paths_info.append((current_path, True, path_id))

        # 3. Filter/truncate paths based on final_member
        result_paths_intermediate = []
        if final_member is not None:
            for full_path, _, path_id in complete_paths_info:
                try:
                    index = full_path.index(final_member)
                    truncated_path = full_path[: index + 1]
                    # Determine if final_member was the actual end of the *full* path
                    is_final_segment = index == len(full_path) - 1
                    result_paths_intermediate.append(
                        (truncated_path, is_final_segment, path_id)
                    )
                except ValueError:
                    # final_member not found in this path, skip it
                    continue
        else:
            # No final_member specified, use all complete paths
            # Correctly mark them as final since they are full paths
            result_paths_intermediate = [
                (p, True, pid) for p, _, pid in complete_paths_info
            ]

        # 4. Apply uniqueness filter to the result
        if unique:
            final_result_paths = []
            seen_paths_tuples = set()
            for path, is_final, path_id in result_paths_intermediate:
                path_tuple = tuple(path)
                if path_tuple not in seen_paths_tuples:
                    seen_paths_tuples.add(path_tuple)
                    final_result_paths.append((path, is_final, path_id))
            return final_result_paths
        else:
            return result_paths_intermediate

    @transaction.atomic
    def get_new_path_id(self) -> int:
        """
        Generates a new unique path ID for the current content type atomically.

        Returns:
            Integer: New unique path ID

        Process:
        1. Gets or creates PathId record for current content type within a transaction.
        2. Locks the row for update.
        3. Atomically increments counter using F() expression.
        4. Refreshes the object to get the updated value.
        5. Returns new unique ID.
        """
        if not self.content_type:
            self.content_type = ContentType.objects.get_for_model(self.model)

        # Lock the row and get or create within the transaction
        path_id_record, created = PathId.objects.select_for_update().get_or_create(
            content_type=self.content_type,
            defaults={"value": 0},  # Start at 0, will be incremented to 1 first time
        )

        # Atomically increment the value using F expression
        path_id_record.value = F("value") + 1  # type: ignore
        path_id_record.save()

        # Refresh from DB to get the actual value generated by the database
        path_id_record.refresh_from_db()

        # After refresh, path_id_record.value will be an int
        result: int = path_id_record.value  # type: ignore
        return result
