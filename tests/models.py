from django.db import models

# Mock Entity for testing
from apps.dag.models import DAGEntity, DAGLinksManager


class MockEntity(models.Model, DAGEntity):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100)

    class Meta:
        app_label = "dag_tests"

    def __str__(self):
        return self.name


# Mock DAG Link model for testing
class MockDAGLink(models.Model):
    entity = models.ForeignKey(
        MockEntity, on_delete=models.CASCADE, related_name="as_child"
    )
    parent = models.ForeignKey(
        MockEntity, on_delete=models.CASCADE, related_name="as_parent"
    )
    path_id = models.IntegerField()
    depth = models.IntegerField()
    weight = models.IntegerField(default=1)
    label = models.CharField(max_length=100, null=True, blank=True)

    class Meta:
        app_label = "dag_tests"

    objects: DAGLinksManager[MockEntity, "MockDAGLink"] = DAGLinksManager[
        MockEntity, "MockDAGLink"
    ]()
