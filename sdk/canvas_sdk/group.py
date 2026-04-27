from canvas_sdk.canvas_object import CanvasObject
from canvas_sdk.collaboration import Collaboration
from canvas_sdk.discussion_topic import DiscussionTopic
from canvas_sdk.exceptions import RequiredFieldMissing
from canvas_sdk.external_feed import ExternalFeed
from canvas_sdk.folder import Folder
from canvas_sdk.license import License
from canvas_sdk.paginated_list import PaginatedList
from canvas_sdk.tab import Tab
from canvas_sdk.upload import FileOrPathLike, Uploader
from canvas_sdk.usage_rights import UsageRights
from canvas_sdk.util import combine_kwargs, is_multivalued, obj_or_id


class Group(CanvasObject):
    def __str__(self):
        return "{} ({})".format(self.name, self.id)

    def create_content_migration(self, migration_type, **kwargs):
        """
        Create a content migration.

        :calls: `POST /api/v1/groups/:group_id/content_migrations \
        <https://canvas.instructure.com/doc/api/content_migrations.html#method.content_migrations.create>`_

        :param migration_type: The migrator type to use in this migration
        :type migration_type: str or :class:`canvas_sdk.content_migration.Migrator`

        :rtype: :class:`canvas_sdk.content_migration.ContentMigration`
        """
        from canvas_sdk.content_migration import ContentMigration, Migrator

        if isinstance(migration_type, Migrator):
            kwargs["migration_type"] = migration_type.type
        elif isinstance(migration_type, str):
            kwargs["migration_type"] = migration_type
        else:
            raise TypeError("Parameter migration_type must be of type Migrator or str")

        response = self._requester.request(
            "POST",
            "groups/{}/content_migrations".format(self.id),
            _kwargs=combine_kwargs(**kwargs),
        )

        response_json = response.json()
        response_json.update({"group_id": self.id})

        return ContentMigration(self._requester, response_json)

    def create_discussion_topic(self, **kwargs):
        """
        Creates a new discussion topic for the course or group.

        :calls: `POST /api/v1/groups/:group_id/discussion_topics \
        <https://canvas.instructure.com/doc/api/discussion_topics.html#method.discussion_topics.create>`_

        :rtype: :class:`canvas_sdk.discussion_topic.DiscussionTopic`
        """
        response = self._requester.request(
            "POST",
            "groups/{}/discussion_topics".format(self.id),
            _kwargs=combine_kwargs(**kwargs),
        )

        response_json = response.json()
        response_json.update({"group_id": self.id})

        return DiscussionTopic(self._requester, response_json)

    def create_external_feed(self, url, **kwargs):
        """
        Create a new external feed for the group.

        :calls: `POST /api/v1/groups/:group_id/external_feeds \
        <https://canvas.instructure.com/doc/api/announcement_external_feeds.html#method.external_feeds.create>`_

        :param url: The urlof the external rss or atom feed
        :type url: str
        :rtype: :class:`canvas_sdk.external_feed.ExternalFeed`
        """
        response = self._requester.request(
            "POST",
            "groups/{}/external_feeds".format(self.id),
            url=url,
            _kwargs=combine_kwargs(**kwargs),
        )
        return ExternalFeed(self._requester, response.json())

    def create_folder(self, name, **kwargs):
        """
        Creates a folder in this group.

        :calls: `POST /api/v1/groups/:group_id/folders \
        <https://canvas.instructure.com/doc/api/files.html#method.folders.create>`_

        :param name: The name of the folder.
        :type name: str
        :rtype: :class:`canvas_sdk.folder.Folder`
        """
        response = self._requester.request(
            "POST",
            "groups/{}/folders".format(self.id),
            name=name,
            _kwargs=combine_kwargs(**kwargs),
        )
        return Folder(self._requester, response.json())

    def create_membership(self, user, **kwargs):
        """
        Join, or request to join, a group, depending on the join_level of the group.
        If the membership or join request already exists, then it is simply returned.

        :calls: `POST /api/v1/groups/:group_id/memberships \
        <https://canvas.instructure.com/doc/api/groups.html#method.group_memberships.create>`_

        :param user: The object or ID of the user.
        :type user: :class:`canvas_sdk.user.User` or int

        :rtype: :class:`canvas_sdk.group.GroupMembership`
        """
        from canvas_sdk.user import User

        user_id = obj_or_id(user, "user", (User,))

        response = self._requester.request(
            "POST",
            "groups/{}/memberships".format(self.id),
            user_id=user_id,
            _kwargs=combine_kwargs(**kwargs),
        )
        return GroupMembership(self._requester, response.json())

    def create_page(self, wiki_page, **kwargs):
        """
        Create a new wiki page.

        :calls: `POST /api/v1/groups/:group_id/pages \
        <https://canvas.instructure.com/doc/api/pages.html#method.wiki_pages_api.create>`_

        :param wiki_page: Details about the page to create.
        :type wiki_page: dict
        :returns: The created page.
        :rtype: :class:`canvas_sdk.page.Page`
        """
        from canvas_sdk.course import Page

        if isinstance(wiki_page, dict) and "title" in wiki_page:
            kwargs["wiki_page"] = wiki_page
        else:
            raise RequiredFieldMissing("Dictionary with key 'title' is required.")

        response = self._requester.request(
            "POST", "groups/{}/pages".format(self.id), _kwargs=combine_kwargs(**kwargs)
        )

        page_json = response.json()
        page_json.update({"group_id": self.id})

        return Page(self._requester, page_json)

    def delete(self, **kwargs):
        """
        Delete a group.

        :calls: `DELETE /api/v1/groups/:group_id \
        <https://canvas.instructure.com/doc/api/groups.html#method.groups.destroy>`_

        :rtype: :class:`canvas_sdk.group.Group`
        """
        response = self._requester.request(
            "DELETE", "groups/{}".format(self.id), _kwargs=combine_kwargs(**kwargs)
        )
        return Group(self._requester, response.json())

    def delete_external_feed(self, feed, **kwargs):
        """
        Deletes the external feed.

        :calls: `DELETE /api/v1/groups/:group_id/external_feeds/:external_feed_id \
        <https://canvas.instructure.com/doc/api/announcement_external_feeds.html#method.external_feeds.destroy>`_

        :param feed: The object or id of the feed to be deleted.
        :type feed: :class:`canvas_sdk.external_feed.ExternalFeed` or int

        :rtype: :class:`canvas_sdk.external_feed.ExternalFeed`
        """
        from canvas_sdk.external_feed import ExternalFeed

        feed_id = obj_or_id(feed, "feed", (ExternalFeed,))

        response = self._requester.request(
            "DELETE",
            "groups/{}/external_feeds/{}".format(self.id, feed_id),
            _kwargs=combine_kwargs(**kwargs),
        )
        return ExternalFeed(self._requester, response.json())

    def edit(self, **kwargs):
        """
        Edit a group.

        :calls: `PUT /api/v1/groups/:group_id \
        <https://canvas.instructure.com/doc/api/groups.html#method.groups.update>`_

        :rtype: :class:`canvas_sdk.group.Group`
        """
        response = self._requester.request(
            "PUT", "groups/{}".format(self.id), _kwargs=combine_kwargs(**kwargs)
        )
        return Group(self._requester, response.json())

    def edit_front_page(self, **kwargs):
        """
        Update the title or contents of the front page.

        :calls: `PUT /api/v1/groups/:group_id/front_page \
        <https://canvas.instructure.com/doc/api/pages.html#method.wiki_pages_api.update_front_page>`_

        :rtype: :class:`canvas_sdk.page.Page`
        """
        from canvas_sdk.course import Page

        response = self._requester.request(
            "PUT",
            "groups/{}/front_page".format(self.id),
            _kwargs=combine_kwargs(**kwargs),
        )
        page_json = response.json()
        page_json.update({"group_id": self.id})

        return Page(self._requester, page_json)

    def export_content(self, export_type, **kwargs):
        """
        Begin a content export job for a group.

        :calls: `POST /api/v1/groups/:group_id/content_exports\
        <https://canvas.instructure.com/doc/api/content_exports.html#method.content_exports_api.create>`_

        :param export_type: The type of content to export.
        :type export_type: str

        :rtype: :class:`canvas_sdk.content_export.ContentExport`
        """
        from canvas_sdk.content_export import ContentExport

        kwargs["export_type"] = export_type

        response = self._requester.request(
            "POST",
            "groups/{}/content_exports".format(self.id),
            _kwargs=combine_kwargs(**kwargs),
        )
        return ContentExport(self._requester, response.json())

    def get_activity_stream_summary(self, **kwargs):
        """
        Return a summary of the current user's global activity stream.

        :calls: `GET /api/v1/groups/:group_id/activity_stream/summary \
        <https://canvas.instructure.com/doc/api/groups.html#method.groups.activity_stream_summary>`_

        :rtype: dict
        """
        response = self._requester.request(
            "GET",
            "groups/{}/activity_stream/summary".format(self.id),
            _kwargs=combine_kwargs(**kwargs),
        )
        return response.json()

    def get_assignment_override(self, assignment, **kwargs):
        """
        Return override for the specified assignment for this group.

        :param assignment: The assignment to get an override for
        :type assignment: :class:`canvas_sdk.assignment.Assignment` or int

        :calls: `GET /api/v1/groups/:group_id/assignments/:assignment_id/override \
        <https://canvas.instructure.com/doc/api/assignments.html#method.assignment_overrides.group_alias>`_

        :rtype: :class:`canvas_sdk.assignment.AssignmentOverride`
        """
        from canvas_sdk.assignment import Assignment, AssignmentOverride

        assignment_id = obj_or_id(assignment, "assignment", (Assignment,))

        response = self._requester.request(
            "GET", "groups/{}/assignments/{}/override".format(self.id, assignment_id)
        )
        response_json = response.json()
        response_json.update({"course_id": self.course_id})

        return AssignmentOverride(self._requester, response_json)

    def get_collaborations(self, **kwargs):
        """
        Return a list of collaborations for a given course ID.

        :calls: `GET /api/v1/groups/:group_id/collaborations \
        <https://canvas.instructure.com/doc/api/collaborations.html#method.collaborations.api_index>`_

        :rtype: :class:`canvas_sdk.collaboration.Collaboration`
        """
        return PaginatedList(
            Collaboration,
            self._requester,
            "GET",
            "groups/{}/collaborations".format(self.id),
            _root="collaborations",
            kwargs=combine_kwargs(**kwargs),
        )

    def get_content_export(self, content_export, **kwargs):
        """
        Return information about a single content export.

        :calls: `GET /api/v1/groups/:group_id/content_exports/:id\
        <https://canvas.instructure.com/doc/api/content_exports.html#method.content_exports_api.show>`_

        :param content_export: The object or ID of the content export to show.
        :type content_export: int or :class:`canvas_sdk.content_export.ContentExport`

        :rtype: :class:`canvas_sdk.content_export.ContentExport`
        """
        from canvas_sdk.content_export import ContentExport

        export_id = obj_or_id(content_export, "content_export", (ContentExport,))

        response = self._requester.request(
            "GET",
            "groups/{}/content_exports/{}".format(self.id, export_id),
            _kwargs=combine_kwargs(**kwargs),
        )

        return ContentExport(self._requester, response.json())

    def get_content_exports(self, **kwargs):
        """
        Return a paginated list of the past and pending content export jobs for a group.

        :calls: `GET /api/v1/groups/:group_id/content_exports\
        <https://canvas.instructure.com/doc/api/content_exports.html#method.content_exports_api.index>`_

        :rtype: :class:`canvas_sdk.paginated_list.PaginatedList` of
            :class:`canvas_sdk.content_export.ContentExport`
        """
        from canvas_sdk.content_export import ContentExport

        return PaginatedList(
            ContentExport,
            self._requester,
            "GET",
            "groups/{}/content_exports".format(self.id),
            kwargs=combine_kwargs(**kwargs),
        )

    def get_content_migration(self, content_migration, **kwargs):
        """
        Retrive a content migration by its ID

        :calls: `GET /api/v1/groups/:group_id/content_migrations/:id \
        <https://canvas.instructure.com/doc/api/content_migrations.html#method.content_migrations.show>`_

        :param content_migration: The object or ID of the content migration to retrieve.
        :type content_migration: int, str or :class:`canvas_sdk.content_migration.ContentMigration`

        :rtype: :class:`canvas_sdk.content_migration.ContentMigration`
        """
        from canvas_sdk.content_migration import ContentMigration

        migration_id = obj_or_id(
            content_migration, "content_migration", (ContentMigration,)
        )

        response = self._requester.request(
            "GET",
            "groups/{}/content_migrations/{}".format(self.id, migration_id),
            _kwargs=combine_kwargs(**kwargs),
        )

        response_json = response.json()
        response_json.update({"group_id": self.id})

        return ContentMigration(self._requester, response_json)

    def get_content_migrations(self, **kwargs):
        """
        List content migrations that the current account can view or manage.

        :calls: `GET /api/v1/groups/:group_id/content_migrations/ \
        <https://canvas.instructure.com/doc/api/content_migrations.html#method.content_migrations.index>`_

        :rtype: :class:`canvas_sdk.paginated_list.PaginatedList` of
            :class:`canvas_sdk.content_migration.ContentMigration`
        """
        from canvas_sdk.content_migration import ContentMigration

        return PaginatedList(
            ContentMigration,
            self._requester,
            "GET",
            "groups/{}/content_migrations".format(self.id),
            {"group_id": self.id},
            _kwargs=combine_kwargs(**kwargs),
        )

    def get_discussion_topic(self, topic, **kwargs):
        """
        Return data on an individual discussion topic.

        :calls: `GET /api/v1/groups/:group_id/discussion_topics/:topic_id \
        <https://canvas.instructure.com/doc/api/discussion_topics.html#method.discussion_topics_api.show>`_

        :param topic: The object or ID of the discussion topic.
        :type topic: :class:`canvas_sdk.discussion_topic.DiscussionTopic` or int

        :rtype: :class:`canvas_sdk.discussion_topic.DiscussionTopic`
        """
        topic_id = obj_or_id(topic, "topic", (DiscussionTopic,))

        response = self._requester.request(
            "GET",
            "groups/{}/discussion_topics/{}".format(self.id, topic_id),
            _kwargs=combine_kwargs(**kwargs),
        )

        response_json = response.json()
        response_json.update({"group_id": self.id})

        return DiscussionTopic(self._requester, response_json)

    def get_discussion_topics(self, **kwargs):
        """
        Returns the paginated list of discussion topics for this course or group.

        :calls: `GET /api/v1/groups/:group_id/discussion_topics \
        <https://canvas.instructure.com/doc/api/discussion_topics.html#method.discussion_topics.index>`_

        :rtype: :class:`canvas_sdk.paginated_list.PaginatedList` of
            :class:`canvas_sdk.discussion_topic.DiscussionTopic`
        """

        return PaginatedList(
            DiscussionTopic,
            self._requester,
            "GET",
            "groups/{}/discussion_topics".format(self.id),
            {"group_id": self.id},
            _kwargs=combine_kwargs(**kwargs),
        )

    def get_external_feeds(self, **kwargs):
        """
        Returns the list of External Feeds this group.

        :calls: `GET /api/v1/groups/:group_id/external_feeds \
        <https://canvas.instructure.com/doc/api/announcement_external_feeds.html#method.external_feeds.index>`_

        :rtype: :class:`canvas_sdk.paginated_list.PaginatedList` of
            :class:`canvas_sdk.external_feed.ExternalFeed`
        """
        from canvas_sdk.external_feed import ExternalFeed

        return PaginatedList(
            ExternalFeed,
            self._requester,
            "GET",
            "groups/{}/external_feeds".format(self.id),
        )

    def get_file(self, file, **kwargs):
        """
        Return the standard attachment json object for a file.

        :calls: `GET /api/v1/groups/:group_id/files/:id \
        <https://canvas.instructure.com/doc/api/files.html#method.files.api_show>`_

        :param file: The object or ID of the file to retrieve.
        :type file: :class:`canvas_sdk.file.File` or int

        :rtype: :class:`canvas_sdk.file.File`
        """
        from canvas_sdk.file import File

        file_id = obj_or_id(file, "file", (File,))

        response = self._requester.request(
            "GET",
            "groups/{}/files/{}".format(self.id, file_id),
            _kwargs=combine_kwargs(**kwargs),
        )
        return File(self._requester, response.json())

    def get_file_quota(self, **kwargs):
        """
        Returns the total and used storage quota for the group.

        :calls: `GET /api/v1/groups/:group_id/files/quota \
        <https://canvas.instructure.com/doc/api/files.html#method.files.api_quota>`_

        :rtype: dict
        """

        response = self._requester.request(
            "GET",
            "groups/{}/files/quota".format(self.id),
            _kwargs=combine_kwargs(**kwargs),
        )

        return response.json()

    def get_files(self, **kwargs):
        """
        Returns the paginated list of files for the group.

        :calls: `GET /api/v1/groups/:group_id/files \
        <https://canvas.instructure.com/doc/api/files.html#method.files.api_index>`_

        :rtype: :class:`canvas_sdk.paginated_list.PaginatedList` of
            :class:`canvas_sdk.file.File`
        """
        from canvas_sdk.file import File

        return PaginatedList(
            File,
            self._requester,
            "GET",
            "groups/{}/files".format(self.id),
            _kwargs=combine_kwargs(**kwargs),
        )

    def get_folder(self, folder, **kwargs):
        """
        Returns the details for a group's folder

        :calls: `GET /api/v1/groups/:group_id/folders/:id \
        <https://canvas.instructure.com/doc/api/files.html#method.folders.show>`_

        :param folder: The object or ID of the folder to retrieve.
        :type folder: :class:`canvas_sdk.folder.Folder` or int

        :rtype: :class:`canvas_sdk.folder.Folder`
        """
        folder_id = obj_or_id(folder, "folder", (Folder,))

        response = self._requester.request(
            "GET",
            "groups/{}/folders/{}".format(self.id, folder_id),
            _kwargs=combine_kwargs(**kwargs),
        )
        return Folder(self._requester, response.json())

    def get_folders(self, **kwargs):
        """
        Returns the paginated list of all folders for the given group. This will be returned as a
        flat list containing all subfolders as well.

        :calls: `GET /api/v1/groups/:group_id/folders \
        <https://canvas.instructure.com/doc/api/files.html#method.folders.list_all_folders>`_

        :rtype: :class:`canvas_sdk.paginated_list.PaginatedList` of
            :class:`canvas_sdk.folder.Folder`
        """
        return PaginatedList(
            Folder, self._requester, "GET", "groups/{}/folders".format(self.id)
        )

    def get_full_discussion_topic(self, topic, **kwargs):
        """
        Return a cached structure of the discussion topic.

        :calls: `GET /api/v1/groups/:group_id/discussion_topics/:topic_id/view \
        <https://canvas.instructure.com/doc/api/discussion_topics.html#method.discussion_topics_api.view>`_

        :param topic: The object or ID of the discussion topic.
        :type topic: :class:`canvas_sdk.discussion_topic.DiscussionTopic` or int

        :rtype: dict
        """
        topic_id = obj_or_id(topic, "topic", (DiscussionTopic,))

        response = self._requester.request(
            "GET",
            "groups/{}/discussion_topics/{}/view".format(self.id, topic_id),
            _kwargs=combine_kwargs(**kwargs),
        )
        return response.json()

    def get_licenses(self, **kwargs):
        """
        Returns a paginated list of the licenses that can be applied to the
        files under the group scope

        :calls: `GET /api/v1/groups/:group_id/content_licenses \
        <https://canvas.instructure.com/doc/api/files.html#method.usage_rights.licenses>`_

        :rtype: :class:`canvas_sdk.paginated_list.PaginatedList` of
            :class:`canvas_sdk.license.License`
        """

        return PaginatedList(
            License,
            self._requester,
            "GET",
            "groups/{}/content_licenses".format(self.id),
            _kwargs=combine_kwargs(**kwargs),
        )

    def get_membership(self, user, membership_type, **kwargs):
        """
        List users in a group.

        :calls: `GET /api/v1/groups/:group_id/users/:user_id \
            <https://canvas.instructure.com/doc/api/groups.html#method.group_memberships.show>`_

            or `GET /api/v1/groups/:group_id/memberships/:membership_id
            <https://canvas.instructure.com/doc/api/groups.html#method.group_memberships.show>`_

        :param user: list of user ids
        :type user: :class:`canvas_sdk.user.User` or int

        :rtype: :class:`canvas_sdk.group.GroupMembership`
        """
        from canvas_sdk.user import User

        user_id = obj_or_id(user, "user", (User,))

        response = self._requester.request(
            "GET",
            "groups/{}/{}/{}".format(self.id, membership_type, user_id),
            _kwargs=combine_kwargs(**kwargs),
        )
        return GroupMembership(self._requester, response.json())

    def get_memberships(self, **kwargs):
        """
        List users in a group.

        :calls: `GET /api/v1/groups/:group_id/memberships \
        <https://canvas.instructure.com/doc/api/groups.html#method.group_memberships.index>`_

        :rtype: :class:`canvas_sdk.paginated_list.PaginatedList` of
            :class:`canvas_sdk.group.GroupMembership`
        """
        return PaginatedList(
            GroupMembership,
            self._requester,
            "GET",
            "groups/{}/memberships".format(self.id),
            _kwargs=combine_kwargs(**kwargs),
        )

    def get_migration_systems(self, **kwargs):
        """
        Return a list of migration systems.

        :calls: `GET /api/v1/groups/:group_id/content_migrations/migrators \
        <https://canvas.instructure.com/doc/api/content_migrations.html#method.content_migrations.available_migrators>`_

        :rtype: :class:`canvas_sdk.paginated_list.PaginatedList` of
            :class:`canvas_sdk.content_migration.Migrator`
        """
        from canvas_sdk.content_migration import Migrator

        return PaginatedList(
            Migrator,
            self._requester,
            "GET",
            "groups/{}/content_migrations/migrators".format(self.id),
            _kwargs=combine_kwargs(**kwargs),
        )

    def get_page(self, url, **kwargs):
        """
        Retrieve the contents of a wiki page.

        :calls: `GET /api/v1/groups/:group_id/pages/:url \
        <https://canvas.instructure.com/doc/api/pages.html#method.wiki_pages_api.show>`_

        :param url: The url for the page.
        :type url: str
        :returns: The specified page.
        :rtype: :class:`canvas_sdk.groups.Group`
        """
        from canvas_sdk.course import Page

        response = self._requester.request(
            "GET",
            "groups/{}/pages/{}".format(self.id, url),
            _kwargs=combine_kwargs(**kwargs),
        )
        page_json = response.json()
        page_json.update({"group_id": self.id})

        return Page(self._requester, page_json)

    def get_pages(self, **kwargs):
        """
        List the wiki pages associated with a group.

        :calls: `GET /api/v1/groups/:group_id/pages \
        <https://canvas.instructure.com/doc/api/pages.html#method.wiki_pages_api.index>`_

        :rtype: :class:`canvas_sdk.paginated_list.PaginatedList` of
            :class:`canvas_sdk.page.Page`
        """
        from canvas_sdk.course import Page

        return PaginatedList(
            Page,
            self._requester,
            "GET",
            "groups/{}/pages".format(self.id),
            {"group_id": self.id},
            _kwargs=combine_kwargs(**kwargs),
        )

    def get_tabs(self, **kwargs):
        """
        List available tabs for a group.
        Returns a list of navigation tabs available in the current context.

        :calls: `GET /api/v1/groups/:group_id/tabs \
        <https://canvas.instructure.com/doc/api/tabs.html#method.tabs.index>`_

        :rtype: :class:`canvas_sdk.paginated_list.PaginatedList` of
            :class:`canvas_sdk.tab.Tab`
        """
        return PaginatedList(
            Tab,
            self._requester,
            "GET",
            "groups/{}/tabs".format(self.id),
            {"group_id": self.id},
            _kwargs=combine_kwargs(**kwargs),
        )

    def get_users(self, **kwargs):
        """
        List users in a group.

        :calls: `GET /api/v1/groups/:group_id/users \
        <https://canvas.instructure.com/doc/api/groups.html#method.groups.users>`_

        :rtype: :class:`canvas_sdk.paginated_list.PaginatedList` of
            :class:`canvas_sdk.user.User`
        """
        from canvas_sdk.user import User

        return PaginatedList(
            User,
            self._requester,
            "GET",
            "groups/{}/users".format(self.id),
            _kwargs=combine_kwargs(**kwargs),
        )

    def invite(self, invitees, **kwargs):
        """
        Invite users to group.

        :calls: `POST /api/v1/groups/:group_id/invite \
        <https://canvas.instructure.com/doc/api/groups.html#method.groups.invite>`_

        :param invitees: list of user ids
        :type invitees: integer list

        :rtype: :class:`canvas_sdk.paginated_list.PaginatedList` of
            :class:`canvas_sdk.group.GroupMembership`
        """
        kwargs["invitees"] = invitees
        return PaginatedList(
            GroupMembership,
            self._requester,
            "POST",
            "groups/{}/invite".format(self.id),
            _kwargs=combine_kwargs(**kwargs),
        )

    def preview_html(self, html, **kwargs):
        """
        Preview HTML content processed for this course.

        :calls: `POST /api/v1/groups/:group_id/preview_html \
        <https://canvas.instructure.com/doc/api/groups.html#method.groups.preview_html>`_

        :param html: The HTML code to preview.
        :type html: str
        :rtype: str
        """
        response = self._requester.request(
            "POST",
            "groups/{}/preview_html".format(self.id),
            html=html,
            _kwargs=combine_kwargs(**kwargs),
        )
        return response.json().get("html", "")

    def remove_usage_rights(self, **kwargs):
        """
        Removes the usage rights for specified files that are under the current group scope

        :calls: `DELETE /api/v1/groups/:group_id/usage_rights \
        <https://canvas.instructure.com/doc/api/files.html#method.usage_rights.remove_usage_rights>`_

        :rtype: dict
        """
        response = self._requester.request(
            "DELETE",
            "groups/{}/usage_rights".format(self.id),
            _kwargs=combine_kwargs(**kwargs),
        )

        return response.json()

    def remove_user(self, user, **kwargs):
        """
        Leave a group if allowed.

        :calls: `DELETE /api/v1/groups/:group_id/users/:user_id \
        <https://canvas.instructure.com/doc/api/groups.html#method.group_memberships.destroy>`_

        :param user: The user object or ID to remove from the group.
        :type user: :class:`canvas_sdk.user.User` or int

        :rtype: :class:`canvas_sdk.user.User`
        """
        from canvas_sdk.user import User

        user_id = obj_or_id(user, "user", (User,))

        response = self._requester.request(
            "DELETE",
            "groups/{}/users/{}".format(self.id, user_id),
            _kwargs=combine_kwargs(**kwargs),
        )
        return User(self._requester, response.json())

    def reorder_pinned_topics(self, order, **kwargs):
        """
        Puts the pinned discussion topics in the specified order.
        All pinned topics should be included.

        :calls: `POST /api/v1/groups/:group_id/discussion_topics/reorder \
        <https://canvas.instructure.com/doc/api/discussion_topics.html#method.discussion_topics.reorder>`_

        :param order: The ids of the pinned discussion topics in the desired order.
            e.g. [104, 102, 103]
        :type order: iterable sequence of values

        :rtype: :class:`canvas_sdk.paginated_list.PaginatedList` of
            :class:`canvas_sdk.discussion_topic.DiscussionTopic`
        """
        # Convert list or tuple to comma-separated string
        if is_multivalued(order):
            order = ",".join([str(topic_id) for topic_id in order])

        # Check if is a string with commas
        if not isinstance(order, str) or "," not in order:
            raise ValueError("Param `order` must be a list, tuple, or string.")

        kwargs["order"] = order

        response = self._requester.request(
            "POST",
            "groups/{}/discussion_topics/reorder".format(self.id),
            _kwargs=combine_kwargs(**kwargs),
        )

        return response.json().get("reorder")

    def resolve_path(self, full_path=None, **kwargs):
        """
        Returns the paginated list of all of the folders in the given
        path starting at the group root folder. Returns root folder if called
        with no arguments.

        :calls: `GET /api/v1/groups/group_id/folders/by_path/*full_path \
        <https://canvas.instructure.com/doc/api/files.html#method.folders.resolve_path>`_

        :param full_path: Full path to resolve, relative to group root.
        :type full_path: string

        :rtype: :class:`canvas_sdk.paginated_list.PaginatedList` of
            :class:`canvas_sdk.folder.Folder`
        """

        if full_path:
            return PaginatedList(
                Folder,
                self._requester,
                "GET",
                "groups/{0}/folders/by_path/{1}".format(self.id, full_path),
                _kwargs=combine_kwargs(**kwargs),
            )
        else:
            return PaginatedList(
                Folder,
                self._requester,
                "GET",
                "groups/{0}/folders/by_path".format(self.id),
                _kwargs=combine_kwargs(**kwargs),
            )

    def set_usage_rights(self, **kwargs):
        """
        Changes the usage rights for specified files that are under the current group scope

        :calls: `PUT /api/v1/groups/:group_id/usage_rights \
        <https://canvas.instructure.com/doc/api/files.html#method.usage_rights.set_usage_rights>`_

        :rtype: :class:`canvas_sdk.usage_rights.UsageRights`
        """

        response = self._requester.request(
            "PUT",
            "groups/{}/usage_rights".format(self.id),
            _kwargs=combine_kwargs(**kwargs),
        )

        return UsageRights(self._requester, response.json())

    def show_front_page(self, **kwargs):
        """
        Retrieve the content of the front page.

        :calls: `GET /api/v1/groups/:group_id/front_page \
        <https://canvas.instructure.com/doc/api/pages.html#method.wiki_pages_api.show_front_page>`_

        :rtype: :class:`canvas_sdk.group.Group`
        """
        from canvas_sdk.course import Page

        response = self._requester.request(
            "GET",
            "groups/{}/front_page".format(self.id),
            _kwargs=combine_kwargs(**kwargs),
        )
        page_json = response.json()
        page_json.update({"group_id": self.id})

        return Page(self._requester, page_json)

    def update_membership(self, user, **kwargs):
        """
        Accept a membership request, or add/remove moderator rights.

        :calls: `PUT /api/v1/groups/:group_id/users/:user_id \
        <https://canvas.instructure.com/doc/api/groups.html#method.group_memberships.update>`_

        :param user: The object or ID of the user.
        :type user: :class:`canvas_sdk.user.User` or int

        :rtype: :class:`canvas_sdk.group.GroupMembership`
        """
        from canvas_sdk.user import User

        user_id = obj_or_id(user, "user", (User,))

        response = self._requester.request(
            "PUT",
            "groups/{}/users/{}".format(self.id, user_id),
            _kwargs=combine_kwargs(**kwargs),
        )
        return GroupMembership(self._requester, response.json())

    def upload(self, file: FileOrPathLike, **kwargs):
        """
        Upload a file to the group.
        Only those with the 'Manage Files' permission on a group can upload files to the group.
        By default, this is anybody participating in the group, or any admin over the group.

        :calls: `POST /api/v1/groups/:group_id/files \
        <https://canvas.instructure.com/doc/api/groups.html#method.groups.create_file>`_

        :param path: The path of the file to upload.
        :type path: str
        :param file: The file or path of the file to upload.
        :type file: file or str
        :returns: True if the file uploaded successfully, False otherwise, \
                    and the JSON response from the API.
        :rtype: tuple
        """

        return Uploader(
            self._requester, "groups/{}/files".format(self.id), file, **kwargs
        ).start()


class GroupMembership(CanvasObject):
    def __str__(self):
        return "{} - {} ({})".format(self.user_id, self.group_id, self.id)

    def remove_self(self, **kwargs):
        """
        Leave a group if allowed.

        :calls: `DELETE /api/v1/groups/:group_id/memberships/:membership_id \
        <https://canvas.instructure.com/doc/api/groups.html#method.group_memberships.destroy>`_

        :returns: An empty dictionary
        :rtype: dict
        """
        response = self._requester.request(
            "DELETE",
            "groups/{}/memberships/self".format(self.id),
            _kwargs=combine_kwargs(**kwargs),
        )
        return response.json()

    def remove_user(self, user, **kwargs):
        """
        Remove user from membership.

        :calls: `DELETE /api/v1/groups/:group_id/users/:user_id \
        <https://canvas.instructure.com/doc/api/groups.html#method.group_memberships.destroy>`_

        :param user: The user object or ID to remove from the group.
        :type user: :class:`canvas_sdk.user.User` or int

        :returns: An empty dictionary
        :rtype: dict
        """
        from canvas_sdk.user import User

        user_id = obj_or_id(user, "user", (User,))

        response = self._requester.request(
            "DELETE",
            "groups/{}/users/{}".format(self.id, user_id),
            _kwargs=combine_kwargs(**kwargs),
        )
        return response.json()

    def update(self, **kwargs):
        """
        Accept a membership request, or add/remove moderator rights.

        :calls: `PUT /api/v1/groups/:group_id/memberships/:membership_id \
        <https://canvas.instructure.com/doc/api/groups.html#method.group_memberships.update>`_

        :rtype: :class:`canvas_sdk.group.GroupMembership`
        """

        response = self._requester.request(
            "PUT",
            "groups/{}/memberships/{}".format(self.group_id, self.id),
            _kwargs=combine_kwargs(**kwargs),
        )
        return GroupMembership(self._requester, response.json())


class GroupCategory(CanvasObject):
    def __str__(self):
        return "{} ({})".format(self.name, self.id)

    def assign_members(self, sync=False, **kwargs):
        """
        Assign unassigned members.

        :calls: `POST /api/v1/group_categories/:group_category_id/assign_unassigned_members \
        <https://canvas.instructure.com/doc/api/group_categories.html#method.group_categories.assign_unassigned_members>`_

        :rtype: :class:`canvas_sdk.paginated_list.PaginatedList` of :class:`canvas_sdk.user.User`
            or :class:`canvas_sdk.progress.Progress`
        """
        from canvas_sdk.progress import Progress
        from canvas_sdk.user import User

        if sync:
            return PaginatedList(
                User,
                self._requester,
                "POST",
                "group_categories/{}/assign_unassigned_members".format(self.id),
                _kwargs=combine_kwargs(**kwargs),
            )
        else:
            response = self._requester.request(
                "POST",
                "group_categories/{}/assign_unassigned_members".format(self.id),
                _kwargs=combine_kwargs(**kwargs),
            )
            return Progress(self._requester, response.json())

    def create_group(self, **kwargs):
        """
        Create a group.

        :calls: `POST /api/v1/group_categories/:group_category_id/groups \
        <https://canvas.instructure.com/doc/api/groups.html#method.groups.create>`_

        :rtype: :class:`canvas_sdk.group.Group`
        """
        response = self._requester.request(
            "POST",
            "group_categories/{}/groups".format(self.id),
            _kwargs=combine_kwargs(**kwargs),
        )
        return Group(self._requester, response.json())

    def delete(self, **kwargs):
        """
        Delete a group category.

        :calls: `DELETE /api/v1/group_categories/:group_category_id \
        <https://canvas.instructure.com/doc/api/group_categories.html#method.group_categories.destroy>`_

        :rtype: empty dict
        """
        response = self._requester.request(
            "DELETE",
            "group_categories/{}".format(self.id),
            _kwargs=combine_kwargs(**kwargs),
        )
        return response.json()

    def get_groups(self, **kwargs):
        """
        List groups in group category.

        :calls: `GET /api/v1/group_categories/:group_category_id/groups \
        <https://canvas.instructure.com/doc/api/group_categories.html#method.group_categories.groups>`_

        :rtype: :class:`canvas_sdk.paginated_list.PaginatedList` of
            :class:`canvas_sdk.group.Group`
        """
        return PaginatedList(
            Group, self._requester, "GET", "group_categories/{}/groups".format(self.id)
        )

    def get_users(self, **kwargs):
        """
        List users in group category.

        :calls: `GET /api/v1/group_categories/:group_category_id/users \
        <https://canvas.instructure.com/doc/api/group_categories.html#method.group_categories.users>`_

        :rtype: :class:`canvas_sdk.paginated_list.PaginatedList` of
            :class:`canvas_sdk.user.User`
        """
        from canvas_sdk.user import User

        return PaginatedList(
            User,
            self._requester,
            "GET",
            "group_categories/{}/users".format(self.id),
            _kwargs=combine_kwargs(**kwargs),
        )

    def update(self, **kwargs):
        """
        Update a group category.

        :calls: `PUT /api/v1/group_categories/:group_category_id \
        <https://canvas.instructure.com/doc/api/group_categories.html#method.group_categories.update>`_

        :rtype: :class:`canvas_sdk.group.GroupCategory`
        """
        response = self._requester.request(
            "PUT",
            "group_categories/{}".format(self.id),
            _kwargs=combine_kwargs(**kwargs),
        )
        return GroupCategory(self._requester, response.json())
