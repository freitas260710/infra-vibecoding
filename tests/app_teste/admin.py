from django.contrib import admin

from infra_vibecoding.admin import AdminSeguro, AdminUsuarioSeguro, InlineTabularSeguro

from .models import ItemPedido, Pedido, UsuarioTeste


class ItemPedidoInline(InlineTabularSeguro):
    model = ItemPedido
    extra = 0


@admin.register(Pedido)
class PedidoAdmin(AdminSeguro):
    list_display = ("titulo", "dono", "valor")
    inlines = [ItemPedidoInline]


admin.site.register(ItemPedido, AdminSeguro)
admin.site.register(UsuarioTeste, AdminUsuarioSeguro)
