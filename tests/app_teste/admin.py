from django.contrib import admin

from infra_vibecoding.admin import AdminSeguro, InlineTabularSeguro

from .models import ItemPedido, Pedido


class ItemPedidoInline(InlineTabularSeguro):
    model = ItemPedido
    extra = 0


@admin.register(Pedido)
class PedidoAdmin(AdminSeguro):
    list_display = ("titulo", "dono", "valor")
    inlines = [ItemPedidoInline]


admin.site.register(ItemPedido, AdminSeguro)
