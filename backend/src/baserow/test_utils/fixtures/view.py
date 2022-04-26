from baserow.contrib.database.fields.models import Field
from baserow.contrib.database.views.models import (
    GridView,
    GridViewFieldOptions,
    GalleryView,
    GalleryViewFieldOptions,
    FormView,
    FormViewFieldOptions,
    ViewFilter,
    ViewSort,
    ViewDecoration,
)


class ViewFixtures:
    def create_grid_view(self, user=None, create_options=True, **kwargs):
        if "table" not in kwargs:
            kwargs["table"] = self.create_database_table(user=user)

        if "name" not in kwargs:
            kwargs["name"] = self.fake.name()

        if "order" not in kwargs:
            kwargs["order"] = 0

        grid_view = GridView.objects.create(**kwargs)
        if create_options:
            self.create_grid_view_field_options(grid_view)
        return grid_view

    def create_grid_view_field_options(self, grid_view, **kwargs):
        return [
            self.create_grid_view_field_option(grid_view, field, **kwargs)
            for field in Field.objects.filter(table=grid_view.table)
        ]

    def create_grid_view_field_option(self, grid_view, field, **kwargs):
        return GridViewFieldOptions.objects.create(
            grid_view=grid_view, field=field, **kwargs
        )

    def create_gallery_view(self, user=None, **kwargs):
        if "table" not in kwargs:
            kwargs["table"] = self.create_database_table(user=user)

        if "name" not in kwargs:
            kwargs["name"] = self.fake.name()

        if "order" not in kwargs:
            kwargs["order"] = 0

        gallery_view = GalleryView.objects.create(**kwargs)
        self.create_gallery_view_field_options(gallery_view)
        return gallery_view

    def create_gallery_view_field_options(self, gallery_view, **kwargs):
        return [
            self.create_gallery_view_field_option(gallery_view, field, **kwargs)
            for field in Field.objects.filter(table=gallery_view.table)
        ]

    def create_gallery_view_field_option(self, gallery_view, field, **kwargs):
        return GalleryViewFieldOptions.objects.create(
            gallery_view=gallery_view, field=field, **kwargs
        )

    def create_form_view(self, user=None, **kwargs):
        if "table" not in kwargs:
            kwargs["table"] = self.create_database_table(user=user)

        if "name" not in kwargs:
            kwargs["name"] = self.fake.name()

        if "order" not in kwargs:
            kwargs["order"] = 0

        form_view = FormView.objects.create(**kwargs)
        self.create_form_view_field_options(form_view)
        return form_view

    def create_form_view_field_options(self, form_view, **kwargs):
        return [
            self.create_form_view_field_option(form_view, field, **kwargs)
            for field in Field.objects.filter(table=form_view.table)
        ]

    def create_form_view_field_option(self, form_view, field, **kwargs):
        return FormViewFieldOptions.objects.create(
            form_view=form_view, field=field, **kwargs
        )

    def create_view_filter(self, user=None, **kwargs):
        if "view" not in kwargs:
            kwargs["view"] = self.create_grid_view(user)

        if "field" not in kwargs:
            kwargs["field"] = self.create_text_field(table=kwargs["view"].table)

        if "type" not in kwargs:
            kwargs["type"] = "equal"

        if "value" not in kwargs:
            kwargs["value"] = self.fake.name()

        return ViewFilter.objects.create(**kwargs)

    def create_view_sort(self, user=None, **kwargs):
        if "view" not in kwargs:
            kwargs["view"] = self.create_grid_view(user)

        if "field" not in kwargs:
            kwargs["field"] = self.create_text_field(table=kwargs["view"].table)

        if "order" not in kwargs:
            kwargs["order"] = "ASC"

        return ViewSort.objects.create(**kwargs)

    def create_view_decoration(self, user=None, **kwargs):
        if "view" not in kwargs:
            kwargs["view"] = self.create_grid_view(user)

        if "type" not in kwargs:
            kwargs["type"] = "left_border_color"

        if "value_provider_type" not in kwargs:
            kwargs["value_provider_type"] = "single_select_color"

        if "value_provider_conf" not in kwargs:
            kwargs["value_provider_conf"] = {}

        if "order" not in kwargs:
            kwargs["order"] = 0

        return ViewDecoration.objects.create(**kwargs)
