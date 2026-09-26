from django.contrib import admin

from infra_vibecoding.admin import AdminSeguro, AdminUsuarioSeguro, InlineTabularSeguro

from .models import Anexo, ItemPedido, Pedido, UsuarioTeste


class ItemPedidoInline(InlineTabularSeguro):
    model = ItemPedido
    extra = 0


@admin.register(Pedido)
class PedidoAdmin(AdminSeguro):
    list_display = ("titulo", "dono", "valor")
    list_filter = ("dono",)  # filtro lateral por ligação (US 2.6)
    search_fields = ("titulo", "dono__email")
    inlines = [ItemPedidoInline]


admin.site.register(ItemPedido, AdminSeguro)
admin.site.register(UsuarioTeste, AdminUsuarioSeguro)
admin.site.register(Anexo, AdminSeguro)
