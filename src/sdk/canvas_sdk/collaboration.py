from canvas_sdk.canvas_object import CanvasObject
from canvas_sdk.paginated_list import PaginatedList
from canvas_sdk.util import combine_kwargs


class Collaboration(CanvasObject):
    def __str__(self):
        return "{} ({})".format(self.document_id, self.id)

    def get_collaborators(self, **kwargs):
        """
        Return a list of collaborators for this collaboration.

        :calls: `GET /api/v1/collaborations/:id/members \
        <https://canvas.instructure.com/doc/api/collaborations.html#method.collaborations.potential_collaborators>`_

        :rtype: :class:`canvas_sdk.collaboration.Collaborator`
        """
        return PaginatedList(
            Collaborator,
            self._requester,
            "GET",
            "collaborations/{}/members".format(self.id),
            _root="collaborators",
            kwargs=combine_kwargs(**kwargs),
        )


class Collaborator(CanvasObject):
    def __str__(self):
        return "{} ({})".format(self.name, self.id)
