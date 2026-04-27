from canvas_sdk.canvas_object import CanvasObject


class License(CanvasObject):
    def __str__(self):
        return "{} {}".format(self.name, self.id)
