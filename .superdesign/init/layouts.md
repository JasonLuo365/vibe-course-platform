# Shared layouts

## `server/app/templates/base.html`

The authenticated teacher-page shell: dark top navigation, optional teacher name, a constrained main container, and Jinja blocks for page content and scripts.

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{% block title %}Vibe 教师端{% endblock %}</title>
  <link rel="stylesheet" href="/static/app.css">
</head>
<body>
  <nav class="navbar">
    <div class="nav-brand">Vibe 教师端</div>
    {% if teacher %}
    <div class="nav-user">{{ teacher.display_name or teacher.username }}</div>
    {% endif %}
  </nav>
  {% if flash %}
  <div class="flash">{{ flash }}</div>
  {% endif %}
  <main class="container">
    {% block content %}{% endblock %}
  </main>
  {% block scripts %}{% endblock %}
</body>
</html>
```

