from django import forms
from django.utils import timezone
from .models import *


# ── Stock forms ──────────────────────────────────────────────────────────────

class StockCreateForm(forms.ModelForm):
    class Meta:
        model = Stock
        fields = ['category', 'item_name', 'quantity', 'image', 'date']
        widgets = {
            'date': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'datetimeinput'}),
        }

    def clean_item_name(self):
        item_name = self.cleaned_data.get('item_name')
        if not item_name:
            raise forms.ValidationError('Item name is required.')
        return item_name

    def clean_quantity(self):
        qty = self.cleaned_data.get('quantity')
        if qty is not None and qty < 0:
            raise forms.ValidationError('Quantity cannot be negative.')
        return qty


class StockUpdateForm(forms.ModelForm):
    class Meta:
        model = Stock
        fields = ['category', 'item_name', 'quantity', 'image']

    def clean_quantity(self):
        qty = self.cleaned_data.get('quantity')
        if qty is not None and qty < 0:
            raise forms.ValidationError('Quantity cannot be negative.')
        return qty


class IssueForm(forms.ModelForm):
    class Meta:
        model = Stock
        fields = ['issue_quantity', 'issued_to']

    def clean_issue_quantity(self):
        qty = self.cleaned_data.get('issue_quantity')
        if qty is None or qty <= 0:
            raise forms.ValidationError('Issue quantity must be greater than zero.')
        return qty


class ReceiveForm(forms.ModelForm):
    class Meta:
        model = Stock
        fields = ['receive_quantity']

    def clean_receive_quantity(self):
        qty = self.cleaned_data.get('receive_quantity')
        if qty is None or qty <= 0:
            raise forms.ValidationError('Receive quantity must be greater than zero.')
        return qty


class ReorderLevelForm(forms.ModelForm):
    class Meta:
        model = Stock
        fields = ['re_order']

    def clean_re_order(self):
        level = self.cleaned_data.get('re_order')
        if level is not None and level < 0:
            raise forms.ValidationError('Reorder level cannot be negative.')
        return level


# ── Search forms ─────────────────────────────────────────────────────────────

class StockSearchForm(forms.Form):
    """Advanced search form for View Stock page."""
    category = forms.ModelChoiceField(
        queryset=Category.objects.all(),
        required=False,
        empty_label='All Categories',
    )
    item_name = forms.CharField(required=False, label='Item Name (contains)')
    min_quantity = forms.IntegerField(required=False, label='Min Quantity', min_value=0)
    max_quantity = forms.IntegerField(required=False, label='Max Quantity', min_value=0)
    export_to_CSV = forms.BooleanField(required=False, label='Export to CSV')


class StockHistorySearchForm(forms.Form):
    """Advanced search form for View History page."""
    category = forms.ModelChoiceField(
        queryset=Category.objects.all(),
        required=False,
        empty_label='All Categories',
    )
    item_name = forms.CharField(required=False, label='Item Name (contains)')
    issued_by = forms.CharField(required=False, label='Issued By (contains)')
    received_by = forms.CharField(required=False, label='Received By (contains)')
    start_date = forms.DateField(
        required=False,
        label='From Date',
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'datetimeinput'}),
    )
    end_date = forms.DateField(
        required=False,
        label='To Date',
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'datetimeinput'}),
    )
    min_quantity = forms.IntegerField(required=False, label='Min Qty in Store', min_value=0)
    max_quantity = forms.IntegerField(required=False, label='Max Qty in Store', min_value=0)
    export_to_CSV = forms.BooleanField(required=False, label='Export to CSV')

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get('start_date')
        end = cleaned.get('end_date')
        if start and end and start > end:
            raise forms.ValidationError('Start date must be before end date.')
        min_q = cleaned.get('min_quantity')
        max_q = cleaned.get('max_quantity')
        if min_q is not None and max_q is not None and min_q > max_q:
            raise forms.ValidationError('Min quantity must be ≤ max quantity.')
        return cleaned


# ── Report form ───────────────────────────────────────────────────────────────

REPORT_TYPE_CHOICES = [
    ('stock_summary', 'Stock Summary'),
    ('low_stock', 'Low Stock / Reorder Alert'),
    ('issue_report', 'Issue Report'),
    ('receive_report', 'Receive Report'),
    ('full_history', 'Full Transaction History'),
]

REPORT_FORMAT_CHOICES = [
    ('html', 'View in Browser'),
    ('csv', 'Download CSV'),
]


class ReportForm(forms.Form):
    report_type = forms.ChoiceField(choices=REPORT_TYPE_CHOICES, label='Report Type')
    report_format = forms.ChoiceField(choices=REPORT_FORMAT_CHOICES, label='Format')
    category = forms.ModelChoiceField(
        queryset=Category.objects.all(),
        required=False,
        empty_label='All Categories',
    )
    item_name = forms.CharField(required=False, label='Item Name (contains)')
    start_date = forms.DateField(
        required=False,
        label='From Date',
        widget=forms.DateInput(attrs={'type': 'date'}),
    )
    end_date = forms.DateField(
        required=False,
        label='To Date',
        widget=forms.DateInput(attrs={'type': 'date'}),
    )

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get('start_date')
        end = cleaned.get('end_date')
        if start and end and start > end:
            raise forms.ValidationError('Start date must be before end date.')
        return cleaned


# ── Dependent dropdown form ───────────────────────────────────────────────────

class DependentDropdownForm(forms.ModelForm):
    class Meta:
        model = Person
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['state'].queryset = State.objects.none()
        if 'country' in self.data:
            try:
                country_idm = int(self.data.get('country'))
                self.fields['state'].queryset = State.objects.filter(
                    country_id=country_idm).order_by('name')
            except (ValueError, TypeError):
                pass
        elif self.instance.pk:
            self.fields['state'].queryset = self.instance.country.state_set.order_by('name')

        self.fields['city'].queryset = City.objects.none()
        if 'state' in self.data:
            try:
                state_idm = int(self.data.get('state'))
                self.fields['city'].queryset = City.objects.filter(
                    state_id=state_idm).order_by('name')
            except (ValueError, TypeError):
                pass
        elif self.instance.pk:
            self.fields['city'].queryset = self.instance.state.city_set.order_by('name')


# ── Scrum forms ───────────────────────────────────────────────────────────────

class AddScrumListForm(forms.ModelForm):
    class Meta:
        model = ScrumTitles
        fields = ['lists']


class AddScrumTaskForm(forms.ModelForm):
    class Meta:
        model = Scrums
        fields = ['task', 'task_description', 'task_date']
        widgets = {
            'task_date': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        }


# ── Contacts form ─────────────────────────────────────────────────────────────

class ContactsForm(forms.ModelForm):
    class Meta:
        model = Contacts
        fields = '__all__'
