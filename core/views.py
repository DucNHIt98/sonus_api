from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from core.responses import success


class HealthCheckView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        return success({'status': 'ok'})
