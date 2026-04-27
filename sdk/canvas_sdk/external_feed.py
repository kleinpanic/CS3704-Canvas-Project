from canvas_sdk.canvas_object import CanvasObject


class ExternalFeed(CanvasObject):
    def __str__(self):
        return "{}".format(self.display_name)
