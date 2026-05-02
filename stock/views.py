import csv
import io
import os
from datetime import datetime, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.db.models import Q, Sum, Count, F
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone

from .form import *
from .models import *


# ── Auth ──────────────────────────────────────────────────────────────────────

def new_register(request):
    form = UserCreationForm()
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Account created! Please log in.')
            return redirect('/accounts/login/')
    return render(request, 'stock/register.html', {'form': form})


# ── Dashboard ─────────────────────────────────────────────────────────────────

@login_required
def get_client_ip(request):
    """Home / dashboard view."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    ip = x_forwarded_for.split(',')[0] if x_forwarded_for else request.META.get('REMOTE_ADDR')
    User.objects.get_or_create(user=ip)

    queryset = Stock.objects.select_related('category').all()
    label_item = [s.item_name or '' for s in queryset]
    data = [s.quantity or 0 for s in queryset]
    issue_data = [s.issue_quantity or 0 for s in queryset]
    receive_data = [s.receive_quantity or 0 for s in queryset]
    labels = [str(c.group) for c in Category.objects.all()]

    low_stock_items = queryset.filter(quantity__lte=models.F('re_order'))

    context = {
        'count': User.objects.count(),
        'body': Stock.objects.count(),
        'mind': StockHistory.objects.count(),
        'soul': Category.objects.count(),
        'low_stock_count': low_stock_items.count(),
        'labels': labels,
        'data': data,
        'issue_data': issue_data,
        'receive_data': receive_data,
        'label_item': label_item,
        'low_stock_items': low_stock_items[:5],
    }
    return render(request, 'stock/home.html', context)


# ── Stock CRUD ────────────────────────────────────────────────────────────────

@login_required
def view_stock(request):
    title = "VIEW STOCKS"
    form = StockSearchForm(request.GET or None)
    everything = Stock.objects.select_related('category').all().order_by('-last_updated')

    if form.is_valid():
        category = form.cleaned_data.get('category')
        item_name = form.cleaned_data.get('item_name', '')
        min_qty = form.cleaned_data.get('min_quantity')
        max_qty = form.cleaned_data.get('max_quantity')

        if item_name:
            everything = everything.filter(item_name__icontains=item_name)
        if category:
            everything = everything.filter(category=category)
        if min_qty is not None:
            everything = everything.filter(quantity__gte=min_qty)
        if max_qty is not None:
            everything = everything.filter(quantity__lte=max_qty)

        if form.cleaned_data.get('export_to_CSV'):
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = 'attachment; filename="Stock_Inventory.csv"'
            writer = csv.writer(response)
            writer.writerow(['CATEGORY', 'ITEM NAME', 'QUANTITY', 'REORDER LEVEL',
                             'LAST UPDATED', 'CREATED BY'])
            for stock in everything:
                writer.writerow([
                    stock.category, stock.item_name, stock.quantity,
                    stock.re_order, stock.last_updated, stock.created_by,
                ])
            return response

    context = {'title': title, 'everything': everything, 'form': form}
    return render(request, 'stock/view_stock.html', context)


@login_required
def add_stock(request):
    title = 'Add Stock'
    form = StockCreateForm()
    if request.method == 'POST':
        form = StockCreateForm(request.POST, request.FILES)
        if form.is_valid():
            instance = form.save(commit=False)
            instance.created_by = str(request.user)
            instance.save()
            messages.success(request, f'"{instance.item_name}" added successfully.')
            return redirect('view_stock')
    return render(request, 'stock/add_stock.html', {'form': form, 'title': title})


@login_required
def update_stock(request, pk):
    title = 'Update Stock'
    update = get_object_or_404(Stock, id=pk)
    form = StockUpdateForm(instance=update)
    if request.method == 'POST':
        form = StockUpdateForm(request.POST, request.FILES, instance=update)
        if form.is_valid():
            # Remove old image only when a new one is uploaded
            if request.FILES.get('image') and update.image:
                try:
                    if os.path.exists(update.image.path):
                        os.remove(update.image.path)
                except Exception:
                    pass
            form.save()
            messages.success(request, f'"{update.item_name}" updated successfully.')
            return redirect('view_stock')
    return render(request, 'stock/add_stock.html', {'form': form, 'update': update, 'title': title})


@login_required
def delete_stock(request, pk):
    stock = get_object_or_404(Stock, id=pk)
    name = stock.item_name
    if stock.image:
        try:
            if os.path.exists(stock.image.path):
                os.remove(stock.image.path)
        except Exception:
            pass
    stock.delete()
    messages.success(request, f'"{name}" has been deleted.')
    return redirect('view_stock')


@login_required
def stock_detail(request, pk):
    detail = get_object_or_404(Stock, id=pk)
    history = StockHistory.objects.filter(item_name=detail.item_name).order_by('-last_updated')[:10]
    return render(request, 'stock/stock_detail.html', {'detail': detail, 'history': history})


@login_required
def issue_item(request, pk):
    issue = get_object_or_404(Stock, id=pk)
    form = IssueForm(request.POST or None, instance=issue)
    if form.is_valid():
        issue_qty = form.cleaned_data['issue_quantity']
        if issue_qty > (issue.quantity or 0):
            messages.error(request, f'Insufficient stock. Only {issue.quantity} unit(s) available.')
            return redirect('stock_detail', pk=pk)
        value = form.save(commit=False)
        value.quantity = (issue.quantity or 0) - issue_qty
        value.issued_by = str(request.user)
        value.receive_quantity = 0  # reset transient field
        value.save()
        messages.success(
            request,
            f'Issued {issue_qty} unit(s) of "{value.item_name}". '
            f'{value.quantity} unit(s) remaining.'
        )
        return redirect('stock_detail', pk=value.id)

    context = {
        'title': f'Issue: {issue.item_name}',
        'issue': issue,
        'form': form,
        'username': f'Issued by: {request.user}',
    }
    return render(request, 'stock/add_stock.html', context)


@login_required
def receive_item(request, pk):
    receive = get_object_or_404(Stock, id=pk)
    form = ReceiveForm(request.POST or None, instance=receive)
    if form.is_valid():
        receive_qty = form.cleaned_data['receive_quantity']
        value = form.save(commit=False)
        value.quantity = (receive.quantity or 0) + receive_qty
        value.received_by = str(request.user)
        value.issue_quantity = 0  # reset transient field
        value.save()
        messages.success(
            request,
            f'Received {receive_qty} unit(s) of "{value.item_name}". '
            f'{value.quantity} unit(s) now in store.'
        )
        return redirect('stock_detail', pk=value.id)

    context = {
        'title': f'Receive: {receive.item_name}',
        'receive': receive,
        'form': form,
        'username': f'Received by: {request.user}',
    }
    return render(request, 'stock/add_stock.html', context)


@login_required
def re_order(request, pk):
    order = get_object_or_404(Stock, id=pk)
    form = ReorderLevelForm(request.POST or None, instance=order)
    if form.is_valid():
        value = form.save()
        messages.success(
            request,
            f'Reorder level for "{value.item_name}" updated to {value.re_order}.'
        )
        return redirect('view_stock')
    return render(request, 'stock/add_stock.html', {'form': form, 'value': order,
                                                     'title': f'Reorder Level: {order.item_name}'})


# ── Stock History ─────────────────────────────────────────────────────────────

@login_required
def view_history(request):
    title = "STOCK HISTORY"
    form = StockHistorySearchForm(request.GET or None)
    history = StockHistory.objects.select_related('category').all().order_by('-last_updated')

    if form.is_valid():
        category = form.cleaned_data.get('category')
        item_name = form.cleaned_data.get('item_name', '')
        issued_by = form.cleaned_data.get('issued_by', '')
        received_by = form.cleaned_data.get('received_by', '')
        start_date = form.cleaned_data.get('start_date')
        end_date = form.cleaned_data.get('end_date')
        min_qty = form.cleaned_data.get('min_quantity')
        max_qty = form.cleaned_data.get('max_quantity')

        if item_name:
            history = history.filter(item_name__icontains=item_name)
        if category:
            history = history.filter(category=category)
        if issued_by:
            history = history.filter(issued_by__icontains=issued_by)
        if received_by:
            history = history.filter(received_by__icontains=received_by)
        if start_date:
            history = history.filter(last_updated__date__gte=start_date)
        if end_date:
            history = history.filter(last_updated__date__lte=end_date)
        if min_qty is not None:
            history = history.filter(quantity__gte=min_qty)
        if max_qty is not None:
            history = history.filter(quantity__lte=max_qty)

        if form.cleaned_data.get('export_to_CSV'):
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = 'attachment; filename="Stock_History.csv"'
            writer = csv.writer(response)
            writer.writerow([
                'CATEGORY', 'ITEM NAME', 'QUANTITY', 'ISSUE QUANTITY',
                'RECEIVE QUANTITY', 'RECEIVED BY', 'ISSUED BY', 'ISSUED TO', 'LAST UPDATED',
            ])
            for h in history:
                writer.writerow([
                    h.category, h.item_name, h.quantity, h.issue_quantity,
                    h.receive_quantity, h.received_by, h.issued_by, h.issued_to, h.last_updated,
                ])
            return response

    context = {'title': title, 'history': history, 'form': form}
    return render(request, 'stock/view_history.html', context)


# ── Reports ───────────────────────────────────────────────────────────────────

@login_required
def reports(request):
    """Unified report generation view."""
    form = ReportForm(request.GET or None)
    report_data = None
    report_title = ''
    columns = []

    if form.is_valid():
        rtype = form.cleaned_data['report_type']
        fmt = form.cleaned_data['report_format']
        category = form.cleaned_data.get('category')
        item_name = form.cleaned_data.get('item_name', '')
        start_date = form.cleaned_data.get('start_date')
        end_date = form.cleaned_data.get('end_date')

        # ── Build queryset based on report type ──
        if rtype == 'stock_summary':
            report_title = 'Stock Summary'
            columns = ['Category', 'Item Name', 'Quantity', 'Reorder Level',
                       'Status', 'Last Updated', 'Created By']
            qs = Stock.objects.select_related('category').all().order_by('category__group', 'item_name')
            if category:
                qs = qs.filter(category=category)
            if item_name:
                qs = qs.filter(item_name__icontains=item_name)
            report_data = [
                {
                    'row': [
                        str(s.category), s.item_name, s.quantity, s.re_order,
                        'LOW STOCK' if (s.quantity or 0) <= (s.re_order or 0) else 'OK',
                        s.last_updated.strftime('%Y-%m-%d %H:%M') if s.last_updated else '',
                        s.created_by or '',
                    ],
                    'highlight': (s.quantity or 0) <= (s.re_order or 0),
                }
                for s in qs
            ]

        elif rtype == 'low_stock':
            report_title = 'Low Stock / Reorder Alert'
            columns = ['Category', 'Item Name', 'Current Qty', 'Reorder Level', 'Deficit']
            qs = Stock.objects.select_related('category').filter(
                quantity__lte=models.F('re_order')
            ).order_by('category__group', 'item_name')
            if category:
                qs = qs.filter(category=category)
            if item_name:
                qs = qs.filter(item_name__icontains=item_name)
            report_data = [
                {
                    'row': [
                        str(s.category), s.item_name, s.quantity, s.re_order,
                        (s.re_order or 0) - (s.quantity or 0),
                    ],
                    'highlight': True,
                }
                for s in qs
            ]

        elif rtype in ('issue_report', 'receive_report', 'full_history'):
            if rtype == 'issue_report':
                report_title = 'Issue Report'
                columns = ['Date', 'Category', 'Item Name', 'Issue Qty', 'Issued By', 'Issued To']
                qs = StockHistory.objects.select_related('category').filter(
                    issue_quantity__gt=0
                ).order_by('-last_updated')
            elif rtype == 'receive_report':
                report_title = 'Receive Report'
                columns = ['Date', 'Category', 'Item Name', 'Receive Qty', 'Received By']
                qs = StockHistory.objects.select_related('category').filter(
                    receive_quantity__gt=0
                ).order_by('-last_updated')
            else:
                report_title = 'Full Transaction History'
                columns = ['Date', 'Category', 'Item Name', 'Qty in Store',
                           'Issue Qty', 'Receive Qty', 'Issued By', 'Received By']
                qs = StockHistory.objects.select_related('category').all().order_by('-last_updated')

            if category:
                qs = qs.filter(category=category)
            if item_name:
                qs = qs.filter(item_name__icontains=item_name)
            if start_date:
                qs = qs.filter(last_updated__date__gte=start_date)
            if end_date:
                qs = qs.filter(last_updated__date__lte=end_date)

            if rtype == 'issue_report':
                report_data = [
                    {
                        'row': [
                            h.last_updated.strftime('%Y-%m-%d %H:%M') if h.last_updated else '',
                            str(h.category), h.item_name, h.issue_quantity,
                            h.issued_by or '', h.issued_to or '',
                        ],
                        'highlight': False,
                    }
                    for h in qs
                ]
            elif rtype == 'receive_report':
                report_data = [
                    {
                        'row': [
                            h.last_updated.strftime('%Y-%m-%d %H:%M') if h.last_updated else '',
                            str(h.category), h.item_name, h.receive_quantity,
                            h.received_by or '',
                        ],
                        'highlight': False,
                    }
                    for h in qs
                ]
            else:
                report_data = [
                    {
                        'row': [
                            h.last_updated.strftime('%Y-%m-%d %H:%M') if h.last_updated else '',
                            str(h.category), h.item_name, h.quantity,
                            h.issue_quantity, h.receive_quantity,
                            h.issued_by or '', h.received_by or '',
                        ],
                        'highlight': False,
                    }
                    for h in qs
                ]

        # ── CSV download ──
        if fmt == 'csv' and report_data is not None:
            response = HttpResponse(content_type='text/csv')
            safe_title = report_title.replace(' ', '_')
            response['Content-Disposition'] = f'attachment; filename="{safe_title}.csv"'
            writer = csv.writer(response)
            writer.writerow(columns)
            for item in report_data:
                writer.writerow(item['row'])
            return response

    context = {
        'form': form,
        'report_data': report_data,
        'report_title': report_title,
        'columns': columns,
        'title': 'Reports',
    }
    return render(request, 'stock/reports.html', context)


# ── Dependent dropdown forms ──────────────────────────────────────────────────

@login_required
def dependent_forms(request):
    title = 'Add Person'
    form = DependentDropdownForm()
    if request.method == 'POST':
        form = DependentDropdownForm(request.POST)
        if form.is_valid():
            instance = form.save()
            messages.success(request, f'"{instance.name}" added successfully.')
            return redirect('depend_form_view')
    return render(request, 'stock/add_stock.html', {'form': form, 'title': title})


@login_required
def dependent_forms_update(request, pk):
    title = 'Update Person'
    dependent_update = get_object_or_404(Person, id=pk)
    form = DependentDropdownForm(instance=dependent_update)
    if request.method == 'POST':
        form = DependentDropdownForm(request.POST, instance=dependent_update)
        if form.is_valid():
            form.save()
            messages.success(request, 'Updated successfully.')
            return redirect('depend_form_view')
    return render(request, 'stock/add_stock.html', {
        'title': title, 'dependent_update': dependent_update, 'form': form,
    })


@login_required
def dependent_forms_view(request):
    viewers = Person.objects.select_related('country', 'state', 'city').all()
    return render(request, 'stock/depend_form_view.html', {
        'title': 'People Directory', 'view': viewers,
    })


@login_required
def delete_dependant(request, pk):
    person = get_object_or_404(Person, id=pk)
    name = person.name
    person.delete()
    messages.success(request, f'"{name}" has been deleted.')
    return redirect('depend_form_view')


def load_stats(request):
    country_idm = request.GET.get('country_id')
    states = State.objects.filter(country_id=country_idm).order_by('name')
    return render(request, 'stock/state_dropdown_list_options.html', {'states': states})


def load_cities(request):
    state_main_id = request.GET.get('state_id')
    cities = City.objects.filter(state_id=state_main_id).order_by('name')
    return render(request, 'stock/city_dropdown_list_options.html', {'cities': cities})


# ── Scrumboard ────────────────────────────────────────────────────────────────

@login_required
def scrum_list(request):
    title = 'Scrumboard'
    add = ScrumTitles.objects.all()
    sub = Scrums.objects.all()
    list_form = AddScrumListForm(prefix='list')
    task_form = AddScrumTaskForm(prefix='task')

    if request.method == 'POST':
        if 'list_submit' in request.POST:
            list_form = AddScrumListForm(request.POST, prefix='list')
            if list_form.is_valid():
                list_form.save()
                messages.success(request, 'List added.')
                return redirect('scrumboard')
        elif 'task_submit' in request.POST:
            task_form = AddScrumTaskForm(request.POST, prefix='task')
            if task_form.is_valid():
                task_form.save()
                messages.success(request, 'Task added.')
                return redirect('scrumboard')

    return render(request, 'stock/scrumboard.html', {
        'add': add, 'sub': sub, 'form': list_form, 'task_form': task_form, 'title': title,
    })


# ── Contacts ──────────────────────────────────────────────────────────────────

@login_required
def contact(request):
    title = 'Contacts'
    people = Contacts.objects.all()
    form = ContactsForm()
    if request.method == 'POST':
        form = ContactsForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, 'Contact added successfully.')
            return redirect('contacts')
    return render(request, 'stock/contacts.html', {'people': people, 'form': form, 'title': title})


@login_required
def delete_contact(request, pk):
    person = get_object_or_404(Contacts, id=pk)
    if person.image:
        try:
            if os.path.exists(person.image.path):
                os.remove(person.image.path)
        except Exception:
            pass
    person.delete()
    messages.success(request, 'Contact deleted.')
    return redirect('contacts')
