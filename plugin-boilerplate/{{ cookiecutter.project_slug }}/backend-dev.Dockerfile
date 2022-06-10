# TODO before merge switch back to proper dockerhub image
FROM registry.gitlab.com/bramw/baserow/ci/backend:ci-latest-432-update-plugin-boilterplate-and-docs-to-match-new-docker-usage

USER root

ARG PLUGIN_BUILD_UID
ENV PLUGIN_BUILD_UID=${PLUGIN_BUILD_UID:-9999}
ARG PLUGIN_BUILD_GID
ENV PLUGIN_BUILD_GID=${PLUGIN_BUILD_GID:-9999}

# If we aren't building as the same user that owns all the files in the base
# image/installed plugins we need to chown everything first.
RUN [ "/bin/bash", "-c", "if [[ $PLUGIN_BUILD_UID != '9999' || $PLUGIN_BUILD_GID != '9999' ]] ; then chown -R $PLUGIN_BUILD_UID:$PLUGIN_BUILD_GID /baserow/; fi" ]

# Install your dev dependencies manually.
COPY --chown=$PLUGIN_BUILD_UID:$PLUGIN_BUILD_GID ./plugins/{{ cookiecutter.project_module }}/backend/requirements/dev.txt /tmp/plugin-dev-requirements.txt
RUN . /baserow/venv/bin/activate && pip3 install -r /tmp/plugin-dev-requirements.txt

COPY --chown=$PLUGIN_BUILD_UID:$PLUGIN_BUILD_GID ./plugins/{{ cookiecutter.project_module }}/ /baserow/plugins/{{ cookiecutter.project_module }}/
RUN /baserow/plugins/install_plugin.sh --folder /baserow/plugins/{{ cookiecutter.project_module }} --dev

USER $PLUGIN_BUILD_UID:$PLUGIN_BUILD_GID
ENV DJANGO_SETTINGS_MODULE='baserow.config.settings.dev'
CMD ["django-dev"]
