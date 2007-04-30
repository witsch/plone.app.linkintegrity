from Products.Archetypes.interfaces import IReference
from Products.Archetypes.Field import TextField
from Products.Archetypes.exceptions import ReferenceException
from zope.component import queryUtility
from Products.CMFCore.interfaces import IPropertiesTool
from OFS.interfaces import IItem
from exceptions import LinkIntegrityNotificationException
from interfaces import ILinkIntegrityInfo, IOFSImage
from urlparse import urlsplit, urlunsplit
from parser import extractLinks

referencedRelationship = 'isReferencing'


def findObject(base, path):
    """ traverse to given path and find the upmost object """
    obj = base
    components = path.split('/')
    while components:
        try: child = obj.restrictedTraverse(components[0])
        except: return None, None
        if not IItem.providedBy(child):
            break
        obj = child
        components.pop(0)
    return obj, '/'.join(components)


def getObjectsFromLinks(base, links):
    """ determine actual objects (plus extra paths) refered to by given links """
    objects = []
    url = base.absolute_url()
    scheme, host, path, query, frag = urlsplit(url)
    site = urlunsplit((scheme, host, '', '', ''))
    for link in links:
        s, h, path, q, f = urlsplit(link)
        if (not s and not h) or (s == scheme and h == host):    # relative or local url
            obj, extra = findObject(base, path)
            if obj:
                extra += urlunsplit(('', '', '', q, f))
                objects.append((obj, extra))
    return objects


def modifiedArchetype(obj, event):
    """ an archetype based object was modified """
    try:    # TODO: is this a bug or a needed workaround?
        for ref in obj.getReferences(relationship=referencedRelationship):
            obj.deleteReference(ref)    # only remove forward references
    except AttributeError:
        return
    refs = []
    for field in obj.Schema().fields():
        if isinstance(field, TextField):
            accessor = field.getAccessor(obj)
            links = extractLinks(accessor())
            refs.extend(getObjectsFromLinks(obj, links))
    for ref, extra in refs:
        if IOFSImage.providedBy(ref):
            ref = ref.aq_parent     # use atimage object for scaled images
        try:
            obj.addReference(ref, relationship=referencedRelationship)
        except ReferenceException:
            pass


def referenceRemoved(obj, event):
    """ store information about the removed link integrity reference """
    assert IReference.providedBy(obj)
    assert obj is event.object          # just making sure...
    if not obj.relationship == referencedRelationship:
        return                          # skip for other removed references
    storage = ILinkIntegrityInfo(obj.REQUEST)
    breaches = storage.getIntegrityBreaches()
    breaches.setdefault(obj.getTargetObject(), []).append(obj.getSourceObject())
    storage.setIntegrityBreaches(breaches)


def referencedObjectRemoved(obj, event):
    """ check if the removal was already confirmed or redirect to the form """
    info = ILinkIntegrityInfo(obj.REQUEST)
    
    # first we check the site properties to see if link integrity
    # checking was enabled
    ptool = queryUtility(IPropertiesTool)
    enabled = False
    if ptool is not None:
        props = ptool.site_properties
        enabled = props.getProperty('enable_link_integrity_checks', False)
    if not enabled:
        return
    
    # since the event gets called for every subobject before it's
    # called for the item deleted directly via _delObject (event.object)
    # itself, but we do not want to present the user with a confirmation
    # form for every (referred) subobject, so we remember and skip them...
    info.addDeletedItem(obj)
    if obj is not event.object:
        return
    
    # if the number of expected events has been stored to help us prevent
    # multiple forms (i.e. in folder_delete), we wait for the next event
    # if we know there will be another...
    if info.moreEventsToExpect():
        return
    
    # at this point all subobjects have been removed already, so all
    # link integrity breaches caused by that have been collected as well;
    # if there aren't any (after things have been cleaned up),
    # we keep lurking in the shadows...
    if not info.getIntegrityBreaches():
        return
    
    # if the user has confirmed to remove the currently handled item in a
    # previous confirmation form we won't need it anymore this time around...    
    if info.isConfirmedItem(obj):
        return
    
    # otherwise we raise an exception and pass the object that is supposed
    # to be removed as the exception value so we can use it as the context
    # for the view triggered by the exception;  this is needed since the
    # view is an adapter for the exception and a request, so it gets the
    # exception object as the context, which is not very useful...
    raise LinkIntegrityNotificationException, obj

