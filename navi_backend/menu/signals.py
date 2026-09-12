from django.db.models.signals import post_delete
from django.db.models.signals import post_save

from navi_backend.core.cache import bump_version
from navi_backend.menu.models import Category
from navi_backend.menu.models import Customization
from navi_backend.menu.models import CustomizationGroup
from navi_backend.menu.models import Ingredient
from navi_backend.menu.models import MenuItem
from navi_backend.menu.models import MenuItemIngredient

MENU_CACHE_NAMESPACE = "menu"

_MENU_MODELS = (
    Category,
    Customization,
    CustomizationGroup,
    Ingredient,
    MenuItem,
    MenuItemIngredient,
)


def bump_menu_cache(sender, **kwargs):
    """Orphan every cached menu payload whenever menu content changes."""
    bump_version(MENU_CACHE_NAMESPACE)


for _model in _MENU_MODELS:
    post_save.connect(
        bump_menu_cache,
        sender=_model,
        dispatch_uid=f"menu_cache_save_{_model.__name__}",
    )
    post_delete.connect(
        bump_menu_cache,
        sender=_model,
        dispatch_uid=f"menu_cache_delete_{_model.__name__}",
    )
